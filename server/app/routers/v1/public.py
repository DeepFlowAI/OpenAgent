"""
Public routes — no authentication required.
Used by the chat page (URL mode) and embedded SDK.
"""
import json
import logging
from typing import Any, Callable, Coroutine

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import NotFoundError, UnauthorizedError, ValidationError
from app.core.embed_token import sign_embed_token, verify_embed_token
from app.core.trace import (
    set_conversation_external_id,
    set_request_id,
    set_trace_id,
)
from app.db.deps import get_db
from app.schemas.channel import (
    EmbedTokenRequest,
    EmbedTokenResponse,
    PublicChannelResponse,
)
from app.schemas.agent import EngineConfig
from app.schemas.chat import ChatCancelRequest, ChatRequest
from app.schemas.conversation import ConversationResponse
from app.schemas.conversation_step import (
    ConversationTimelineResponse,
    StepFeedbackResponse,
    StepFeedbackSubmit,
)
from app.schemas.telemetry import TelemetryBatchRequest, TelemetryBatchResponse
from app.services.agent_service import AgentService
from app.services.channel_service import ChannelService
from app.services.detached_chat_stream_service import DetachedChatStreamService
from app.repositories.conversation_repository import ConversationRepository
from app.services.conversation_step_service import ConversationStepService
from app.services.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/channels/{token}", response_model=PublicChannelResponse)
async def get_public_channel(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Get channel info by token — no auth required.

    Returns ``PublicChannelResponse`` which intentionally **omits** ``secret_key``
    and ``tenant_id`` so the browser-facing SDK / chat page never sees them.
    """
    channel = await ChannelService.get_by_token(db, token)
    response = PublicChannelResponse.model_validate(channel)

    if not channel.agent_id:
        return response

    agent = await AgentService.get_by_id(db, channel.agent_id)
    engine_config = EngineConfig(
        **{**EngineConfig().model_dump(), **(agent.engine_config or {})}
    )
    response.conversation_settings = engine_config.conversation_settings
    return response


@router.post(
    "/channels/{token}/embed-token",
    response_model=EmbedTokenResponse,
)
async def sign_embed_token_endpoint(
    token: str,
    body: EmbedTokenRequest,
    x_channel_secret: str = Header(..., alias="X-Channel-Secret"),
    db: AsyncSession = Depends(get_db),
):
    """Sign an embed token for Web SDK / URL mode.

    The caller must provide the channel secret_key via X-Channel-Secret header.
    This endpoint is called by the integrator's **server-side** code — the
    secret_key never reaches the browser.
    """
    channel = await ChannelService.get_by_token(db, token)
    if not channel.secret_key:
        raise ValidationError("Channel has no secret key — generate one first")
    if channel.secret_key != x_channel_secret:
        raise UnauthorizedError("Invalid channel secret key")

    embed_token = sign_embed_token(
        channel.secret_key,
        channel_id=channel.id,
        tenant_id=channel.tenant_id,
        external_user_id=body.external_user_id,
        display_name=body.display_name,
        email=body.email,
        phone=body.phone,
        avatar_url=body.avatar_url,
        source="websdk",
        title=body.title,
        metadata=body.metadata,
        ttl=body.ttl,
    )
    return EmbedTokenResponse(token=embed_token, expires_in=body.ttl)


@router.post("/channels/{token}/chat")
async def public_chat(
    token: str,
    body: ChatRequest,
    embed_token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """SSE streaming chat via channel token — no auth required.

    When `embed_token` query param is provided, the token is verified against
    the channel's secret_key and the customer context is extracted from the
    payload for auto-create conversation scenarios (§5.1 / §5.6).
    """
    channel = await ChannelService.get_by_token(db, token)
    if not channel.agent_id:
        raise NotFoundError("Channel has no agent bound")

    # The Redis detached backend keys its claim/stream/cancel state on
    # client_message_id; validate here (before the StreamingResponse) so a
    # missing key surfaces as a real HTTP 400 rather than an in-stream
    # ``event: error`` swallowed by the SSE generator below.
    if settings.DETACHED_CHAT_BACKEND == "redis" and not body.client_message_id:
        raise ValidationError(
            "client_message_id is required when DETACHED_CHAT_BACKEND=redis"
        )

    agent = await AgentService.get_by_id(db, channel.agent_id)

    body_customer_context = (
        body.customer_context.model_dump(exclude_none=True)
        if body.customer_context
        else None
    )

    # Resolve customer context: embed_token > body.customer_context > None.
    # The URL `test` flag is client-visible request context, so preserve it
    # even when identity/profile fields come from a signed embed token.
    customer_context: dict | None = None
    if embed_token and channel.secret_key:
        payload = verify_embed_token(channel.secret_key, embed_token)
        # Extract §4 customer context fields from token payload
        customer_context = {}
        for key in (
            "external_user_id", "display_name", "email",
            "phone", "avatar_url", "source", "title", "metadata",
        ):
            if key in payload and payload[key] is not None:
                customer_context[key] = payload[key]
        if body_customer_context:
            if body_customer_context.get("is_test") is True:
                customer_context["is_test"] = True
            if body_customer_context.get("channel_source") is not None:
                customer_context["channel_source"] = body_customer_context[
                    "channel_source"
                ]
    elif body_customer_context:
        customer_context = body_customer_context

    if customer_context is None:
        customer_context = {}
    customer_context["source"] = "websdk"
    customer_context["channel_id"] = channel.id

    trace_id = set_trace_id()
    set_request_id(body.request_id)
    if body.conversation_external_id:
        set_conversation_external_id(body.conversation_external_id)
    logger.info(
        "Public chat request — channel_token=%s, agent_id=%s, conversation_id=%s, "
        "conversation_external_id=%s, request_id=%s, trace_id=%s, msg_len=%d, has_embed_token=%s",
        token,
        agent.id,
        body.conversation_id,
        body.conversation_external_id or "-",
        body.request_id or "-",
        trace_id,
        len(body.message),
        bool(embed_token),
    )
    if customer_context:
        logger.info("Customer context — %s", customer_context)

    async def event_generator():
        try:
            stream = DetachedChatStreamService.stream_public_chat(
                channel_token=token,
                agent_id=agent.id,
                user_message=body.message,
                conversation_id=body.conversation_id,
                customer_context=customer_context,
                resume=body.resume,
                client_message_id=body.client_message_id,
                last_event_id=body.last_event_id,
            )
            async for event in stream:
                yield event
        except Exception as e:
            logger.exception("Public chat stream error")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            logger.info("Public chat stream ended")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Trace-Id": trace_id,
        },
    )


@router.post("/channels/{token}/chat/cancel")
async def cancel_public_chat(
    token: str,
    body: ChatCancelRequest,
    db: AsyncSession = Depends(get_db),
):
    """Explicitly cancel a running public Web SDK chat turn.

    Plain SSE disconnects are treated as transport loss and the backend round
    keeps running. This endpoint is only used by the explicit "stop response"
    action; new-chat and switch-conversation detach from the stream without
    cancelling the backend round.
    """
    channel = await ChannelService.get_by_token(db, token)
    if not channel.agent_id:
        raise NotFoundError("Channel has no agent bound")

    cancelled = await DetachedChatStreamService.cancel_public_chat(
        channel_token=token,
        client_message_id=body.client_message_id,
    )
    return {"cancelled": cancelled}


@router.get(
    "/channels/{token}/conversations",
    response_model=list[ConversationResponse],
)
async def list_public_conversations(
    token: str,
    external_user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List conversations for an anonymous user by external_user_id — no auth required."""
    channel = await ChannelService.get_by_token(db, token)
    if not channel.agent_id:
        raise NotFoundError("Channel has no agent bound")
    return await ConversationRepository.get_by_external_user_id(
        db,
        tenant_id=channel.tenant_id,
        agent_id=channel.agent_id,
        external_user_id=external_user_id,
    )


@router.get(
    "/channels/{token}/conversations/{conversation_id}/steps",
    response_model=ConversationTimelineResponse,
)
async def get_public_conversation_steps(
    token: str,
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get conversation timeline/steps — no auth required.

    Validates that the conversation belongs to the channel's tenant + agent
    before returning. Without this, any caller holding ANY channel token could
    enumerate conversation_ids and read other tenants' transcripts.
    """
    channel = await ChannelService.get_by_token(db, token)
    if not channel.agent_id:
        raise NotFoundError("Channel has no agent bound")

    # Ownership guard: the conversation must belong to the same tenant AND
    # the agent bound to this channel. We surface "not found" (not 403) so
    # an attacker can't distinguish "exists but forbidden" from "missing".
    conv = await ConversationRepository.get_by_id(db, conversation_id)
    if (
        conv is None
        or conv.tenant_id != channel.tenant_id
        or conv.agent_id != channel.agent_id
    ):
        raise NotFoundError("Conversation not found")

    # Sub-req 2: end-user history reconstruction must not see incomplete (partial)
    # llm_call steps — those represent failed mid-stream attempts whose content
    # was intentionally discarded by the resume protocol.
    return await ConversationStepService.get_timeline(
        db, conversation_id, include_incomplete=False,
    )


@router.post(
    "/channels/{token}/steps/{step_id}/feedback",
    response_model=StepFeedbackResponse,
)
async def submit_public_step_feedback(
    token: str,
    step_id: int,
    body: StepFeedbackSubmit,
    db: AsyncSession = Depends(get_db),
):
    """Submit or overwrite visitor feedback for one assistant reply step."""
    channel = await ChannelService.get_by_token(db, token)
    return await ConversationStepService.submit_public_feedback(
        db,
        channel=channel,
        step_id=step_id,
        data=body,
    )


# Hard upper bound on the telemetry POST body size, in bytes. A healthy SDK
# batch is ~10–30 KB; this cap is sized at 8× the worst plausible legitimate
# payload (200 events × ~200 bytes each + common ≈ 40 KB) so a real client
# can't trip it, while a malicious client trying to DoS the endpoint with a
# multi-MB JSON gets rejected before any parsing happens.
_TELEMETRY_BODY_BYTES_CAP = 256 * 1024


async def _read_body_with_cap(request: Request, cap: int) -> None:
    """Read the request body with a streaming byte cap and cache it.

    Why this isn't a route-level ``Depends``:

    FastAPI's request-handling order is, per ``fastapi.routing``:

        1. ``await request.body()``      — materialises the full body
        2. JSON parse + Pydantic validate the body field
        3. ``solve_dependencies(...)`` — runs route-level dependencies

    So a 100 MB chunked POST would already be in memory by the time a
    ``Depends(...)`` body-cap check could run. The only FastAPI-supported
    way to intercept BEFORE step 1 is to wrap ``APIRoute.get_route_handler``;
    see :class:`_TelemetryRoute` below.

    Two paths cover both honest and abusive clients:

    * **Trusted Content-Length fast path** — when the header is present
      and within the cap, return immediately without touching the
      stream. The downstream body parser will then read normally. Every
      healthy SDK request takes this path (httpx and ``fetch`` always
      compute Content-Length on JSON bodies).
    * **Stream-read cap path** — when Content-Length is missing
      (chunked transfer-encoding, malformed header, or an attacker
      deliberately omitting it), we consume ``request.stream()``
      ourselves and abort the moment cumulative byte count crosses the
      cap. The accepted bytes are cached on ``request._body`` so the
      downstream body parser uses our buffer instead of trying to
      re-read the (now-exhausted) stream.
    """
    cl_header = request.headers.get("content-length")
    if cl_header is not None:
        try:
            cl = int(cl_header)
        except ValueError:
            cl = None
        else:
            if cl > cap:
                raise ValidationError(
                    f"Telemetry batch too large: {cl} bytes (limit {cap})"
                )
            # Trusted Content-Length within cap → don't touch the
            # stream; let the downstream body parser read it normally.
            return

    # No / invalid Content-Length: stream-read with byte cap. Each
    # iteration receives whatever the ASGI server hands us (typically
    # ≤64 KB chunks). One buffer copy per chunk is unavoidable since
    # the body has to be materialised anyway for JSON parsing — what
    # we save is the worst-case multi-MB allocation that would happen
    # if we let the body parser read first.
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > cap:
            raise ValidationError(
                f"Telemetry batch too large: stream exceeded {cap} bytes"
            )
        chunks.append(chunk)
    # ``Request._body`` is the cache that ``Request.body()`` reads from
    # — if it's already set, ``body()`` returns it without touching the
    # stream. The attribute is private but stable across Starlette
    # versions (it's the very field the public ``body()`` accessor
    # populates and reads). Setting it here makes our buffer the source
    # of truth for the downstream JSON parser.
    request._body = b"".join(chunks)  # type: ignore[attr-defined]


class _TelemetryRoute(APIRoute):
    """APIRoute subclass that enforces ``_TELEMETRY_BODY_BYTES_CAP``
    BEFORE FastAPI's internal body parser materialises the bytes.

    See ``_read_body_with_cap`` for why a custom route class is the only
    correct interception point — the standard ``Depends(...)`` mechanism
    runs after the body has already been read into memory.

    The wrapped handler delegates to the original FastAPI route handler
    after the cap check, so all the normal Pydantic validation, response
    serialisation and exception-handling paths still apply.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def cap_then_handle(request: Request) -> Response:
            # Raises ``ValidationError`` (-> 400 via the project's
            # exception handler) for oversized bodies. The exception
            # propagates up through Starlette's exception middleware
            # exactly like any in-route raise, so no special wiring
            # is needed here.
            await _read_body_with_cap(request, _TELEMETRY_BODY_BYTES_CAP)
            return await original_handler(request)

        return cap_then_handle


# Sub-router with the cap-aware route class. Scoped narrowly so the
# overhead of stream-reading bodies doesn't apply to chat / health /
# embed-token / channel endpoints — those have their own size profile
# (chat bodies are bounded by the schema; auth endpoints take ~200B).
_telemetry_router = APIRouter(route_class=_TelemetryRoute)


@_telemetry_router.post(
    "/channels/{token}/telemetry/events",
    response_model=TelemetryBatchResponse,
)
async def post_telemetry_events(
    token: str,
    body: TelemetryBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Batch-ingest frontend telemetry events — no auth required.

    The endpoint trusts ``channel_token`` as the only auth signal (matching
    the rest of /public/*). Per-event ``trace_id`` / ``conversation_*`` IDs
    are taken from the SDK so the resulting otel_logs rows can be joined
    against the existing backend logs by the log-analyzer Skill recipes.

    Defence layers (outer → inner):
      1. Streaming body cap (``_TelemetryRoute`` + ``_read_body_with_cap``)
         — rejects abusive multi-MB bodies BEFORE FastAPI's body parser
         allocates anything. Honest clients with a Content-Length header
         hit a single integer compare; chunked / unbounded clients are
         stream-read with a running byte counter and aborted at 256 KB.
      2. ``TelemetryBatchRequest.events`` schema cap — bounds the parsed
         list size at ``SCHEMA_MAX_EVENTS_PER_BATCH`` so a payload that
         lies about its content length (or that nginx forwarded with the
         200 MB global limit still in place) still fails fast at the
         Pydantic stage.
      3. Service-layer trim — anything above ``MAX_EVENTS_PER_BATCH``
         goes into ``dropped`` so honest clients aren't 422'd.

    Oversized batches and per-event payloads are silently trimmed (counted
    in ``dropped``) rather than rejected — the SDK's replay-from-localStorage
    path can't usefully recover from a 422, and dropping is recoverable
    (the user-impact metrics are sampled densely enough that a few lost
    events don't blind us to a real incident).
    """
    channel = await ChannelService.get_by_token(db, token)
    return await TelemetryService.ingest(channel=channel, body=body)


# Mount the cap-aware sub-router on the main public router. Done after
# the endpoint is defined so import order doesn't matter.
router.include_router(_telemetry_router)
