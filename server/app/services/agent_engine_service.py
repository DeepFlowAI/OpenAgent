"""
Agent engine execution service — orchestrates LLM calls, tool execution,
step logging, and SSE event streaming for a single chat round.
"""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from enum import Enum
from typing import Awaitable, AsyncIterator, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.trace import (
    get_conversation_external_id,
    get_request_id,
    get_trace_id,
    set_conversation_external_id,
    set_conversation_id,
)
from app.libs.llm import create_llm_client, LLMStreamDelta
from app.libs.llm.base import LLMAPIError, LLMStreamResult
from app.libs.observability import conversation_span, current_span
from app.repositories.agent_repository import AgentRepository
from app.repositories.agent_tool_repository import AgentToolRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.conversation_step_repository import ConversationStepRepository
from app.schemas.agent import EngineConfig
from app.schemas.conversation import ConversationCreate
from app.schemas.conversation_step import StepCreate
from app.services.round_event_buffer import (
    RoundKey,
    format_event_id,
    parse_event_id,
    round_event_buffer,
)
from app.libs.template import render_template

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 20

# Type alias for the optional "is the SSE client still connected?" probe the
# router may inject. Returning True ⇒ disconnected ⇒ we MUST NOT spend more
# upstream LLM tokens retrying for an audience that's already gone.
IsDisconnectedCallback = Callable[[], Awaitable[bool]]


class StreamRetryAction(str, Enum):
    """Pure decision values from the synchronous part of the the stream-level retry spec matrix.

    Kept as a plain enum so the (rather subtle) decision tree can be unit-tested
    in isolation, without spinning up a DB / LLM client / SSE generator.
    """

    GIVE_UP = "give_up"
    SILENT_RETRY = "silent_retry"
    RESET_RETRY = "reset_retry"


# How long a same-conversation retry will wait for an in-flight round to
# release the advisory lock before giving up.
#
# Must be ≥ the longest watchdog ``overall_ms`` the server pushes to clients
# (see ``_watchdog_for``: thinking models legitimately budget 300s for one
# round). Otherwise a weak-network retry that arrives while the original
# request is still streaming a slow thinking-model round trips ConflictError
# at 60s — even though the original would have finished ~240s later and we
# could have served the second request through the buffer fast-path. The
# old 60s value was sized for fast non-thinking models and silently broke
# resume on every reasoning-model reconnect.
#
# Trade-off: a genuinely wedged round now blocks the retry up to ~5.5min
# before failing. We accept that because the ``is_disconnected_cb`` poll
# inside the engine releases the lock as soon as the original request's
# SSE peer goes away (typical mid-retry case), so this ceiling is rarely
# hit in practice — only when the holder is making real progress.
ROUND_LOCK_WAIT_TIMEOUT_SEC = 330.0


@asynccontextmanager
async def _round_advisory_lock(
    db: AsyncSession, conversation_id: int, round_number: int,
) -> AsyncIterator[bool]:
    """Low-level PG advisory lock primitive: try once, yield ``locked``.

    Used directly by tests that need to observe acquire-vs-block behavior;
    production code should prefer :func:`_hold_round_lock` which spins +
    recomputes the lock key as round state advances.

    The lock is session-scoped (not transaction-scoped) so it survives the
    many commits the engine performs while streaming. We always release in
    ``finally`` — but since FastAPI's request-scoped session is closed at
    the end of the request anyway, an unreleased lock would also be GC'd
    by the connection pool when the connection is recycled.
    """
    conn = await db.connection()
    acquired = (await conn.execute(
        text("SELECT pg_try_advisory_lock(:k1, :k2)"),
        {"k1": int(conversation_id), "k2": int(round_number)},
    )).scalar()
    locked = bool(acquired)
    try:
        yield locked
    finally:
        if locked:
            try:
                await conn.execute(
                    text("SELECT pg_advisory_unlock(:k1, :k2)"),
                    {"k1": int(conversation_id), "k2": int(round_number)},
                )
            except Exception as exc:  # noqa: BLE001
                # Connection may have died with the request; pool recycle
                # will reclaim the lock anyway. Don't fail the round on it.
                logger.warning(
                    "Failed to release round advisory lock conv=%s round=%s: %s",
                    conversation_id, round_number, exc,
                )


async def _resolve_round_state(
    db: AsyncSession,
    conv,
    conversation_id: int,
    client_message_id: str | None,
) -> tuple[int, bool]:
    """Return the ``(round_number, resume)`` tuple the engine should use,
    given the current persisted conversation state.

    Two inputs decide the outcome:

    - ``conv.round_count``: how many rounds have already been *completed*
      (incremented only after a clean ``assistant_message`` is written).
    - ``client_message_id``: when the same idempotency key has already been
      bound to a ``user_message`` step, this request is a retry of that
      logical turn — we resume the existing round instead of opening a new
      one.

    Pulling this into a helper lets :func:`_hold_round_lock` re-derive the
    state after every wait cycle, so a request that blocked on a busy lock
    correctly sees any new ``round_count`` advance / new ``user_message``
    that the in-flight request committed while we were waiting.
    """
    round_number = (conv.round_count or 0) + 1
    resume = False
    if client_message_id:
        existing = await ConversationStepRepository.get_user_message_by_client_id(
            db, conversation_id, client_message_id,
        )
        if existing is not None:
            resume = True
            round_number = existing.round_number
    return round_number, resume


@asynccontextmanager
async def _hold_round_lock(
    db: AsyncSession,
    conv,
    conversation_id: int,
    client_message_id: str | None,
    *,
    timeout_sec: float = ROUND_LOCK_WAIT_TIMEOUT_SEC,
) -> AsyncIterator[tuple[int, bool]]:
    """Acquire the per-round advisory lock with a bounded wait.

    Two callers interleave on the same conversation:

    - **Same-turn retry** (same ``client_message_id``): the user's network
      blipped, the SDK reissued the request. The original is still
      streaming. We MUST wait for it to release the lock and then *resume*
      from its persisted state — including replaying ``done`` if it
      already produced a complete ``assistant_message`` while we waited.
    - **Truly concurrent fresh message** (different / no
      ``client_message_id``, brand-new turn): the user sent a follow-up
      while the previous round was still being generated. The new turn
      conceptually belongs to ``round_count + 1`` of the FUTURE state,
      which we can only know after the in-flight round commits its
      counter advance. We wait, then re-derive ``round_number`` from
      the fresh ``conv.round_count`` and try the lock again.

    Yields ``(round_number, resume)`` after the lock is acquired. Both
    values may have shifted from the caller's initial computation if we
    waited through state changes — callers MUST use the yielded values
    inside the body, not their pre-computed ones.

    Times out with :class:`ConflictError` rather than blocking forever, so
    a wedged round can't quietly hang every same-conversation retry. SSE
    routers translate that into ``event: error`` and the SDK surfaces it.
    """
    conn = await db.connection()
    deadline = time.monotonic() + timeout_sec
    poll_sec = 0.1
    locked_round_number: int | None = None
    waited = False

    while True:
        round_number, resume = await _resolve_round_state(
            db, conv, conversation_id, client_message_id,
        )
        acquired = (await conn.execute(
            text("SELECT pg_try_advisory_lock(:k1, :k2)"),
            {"k1": int(conversation_id), "k2": int(round_number)},
        )).scalar()
        if acquired:
            locked_round_number = round_number
            if waited:
                logger.info(
                    "Round lock acquired after wait — conv=%s round=%s resume=%s",
                    conversation_id, round_number, resume,
                )
            break

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warning(
                "Round lock wait timed out — conv=%s round=%s after %.1fs",
                conversation_id, round_number, timeout_sec,
            )
            raise ConflictError(
                f"Conversation {conversation_id} round {round_number} is still "
                f"busy after {int(timeout_sec)}s; please retry shortly"
            )

        # Refresh `conv` so the next loop iteration sees a fresh
        # ``round_count`` (advanced by the in-flight request when its round
        # commits) and any newly-persisted ``user_message`` for our cmid.
        await db.refresh(conv)
        waited = True
        await asyncio.sleep(min(poll_sec, remaining, 2.0))
        poll_sec = min(poll_sec * 1.5, 2.0)

    try:
        yield locked_round_number, resume
    finally:
        try:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:k1, :k2)"),
                {"k1": int(conversation_id), "k2": int(locked_round_number)},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to release round advisory lock conv=%s round=%s: %s",
                conversation_id, locked_round_number, exc,
            )


def decide_stream_retry_action(
    *,
    partial_content_chars: int,
    retry_count: int,
    retry_enabled: bool,
    retry_max: int,
    reset_max_chars: int,
) -> StreamRetryAction:
    """Return the retry action for an "incomplete" stream (stream-level retry spec §4.4).

    Note: the "client disconnected" check lives in the engine main loop because
    it requires an awaitable callback; this function covers the SYNCHRONOUS
    portion of the matrix, which is the part that benefits most from unit tests.

    Decision order matters:
        1. Master switch off ⇒ GIVE_UP (legacy behavior).
        2. Retry budget exhausted ⇒ GIVE_UP.
        3. Already streamed > reset_max_chars ⇒ GIVE_UP (avoid duplicate UX).
        4. Some chars already shown ⇒ RESET_RETRY (must emit assistant_reset).
        5. Otherwise ⇒ SILENT_RETRY (no SSE event needed).
    """
    if not retry_enabled:
        return StreamRetryAction.GIVE_UP
    if retry_count >= retry_max:
        return StreamRetryAction.GIVE_UP
    if partial_content_chars > reset_max_chars:
        return StreamRetryAction.GIVE_UP
    if partial_content_chars > 0:
        return StreamRetryAction.RESET_RETRY
    return StreamRetryAction.SILENT_RETRY


class AgentEngineService:
    """Runs one user turn through the Agent engine, yielding SSE events."""

    @staticmethod
    async def run_chat_round(
        db: AsyncSession,
        agent_id: int,
        user_message: str,
        conversation_id: int | None = None,
        customer_context: dict | None = None,
        resume: bool = False,
        is_disconnected_cb: IsDisconnectedCallback | None = None,
        client_message_id: str | None = None,
        last_event_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Public entry — wraps the engine body with a conversation span so
        the whole chat round (including any nested LLM and tool spans) shows
        up as a single trace tree in the observability backend.

        Implementation lives in `_run_chat_round_impl` to keep the span code
        from drowning out the engine logic.

        ``is_disconnected_cb`` (optional, the stream-level retry spec): when supplied, the engine
        polls it before deciding to retry an incomplete LLM stream — if the SSE
        client has already disconnected we skip the retry to avoid burning
        tokens for an audience that's gone. Routers wire it to
        ``Request.is_disconnected``; tests / non-HTTP callers may leave it None.

        ``client_message_id`` (optional, sub-req 3): client-supplied idempotency
        key. When provided alongside an existing ``conversation_id`` and the
        conversation already has a matching user_message step, the engine
        force-enables resume to avoid duplicate user messages / LLM rounds.
        """
        # Tag every log record emitted during this round with the conversation
        # id, so Grafana / your log backend queries can filter by it directly
        # (single-step), instead of having to first look up the trace_id.
        if conversation_id:
            set_conversation_id(conversation_id)

        span_attrs = {
            "agent.id": agent_id,
            "conversation.id": conversation_id or 0,
            "conversation.external_id": get_conversation_external_id(),
            "conversation.resume": resume,
            "conversation.client_message_id": client_message_id or "",
            "conversation.last_event_id": last_event_id or "",
            "conversation.user_message_len": len(user_message or ""),
            "app.trace_id": get_trace_id(),
            "app.request_id": get_request_id(),
        }
        with conversation_span("chat_round", span_attrs) as span:
            # Bind the inner generator to a local so we can forward
            # ``aclose()`` to it. Without this, a ``GeneratorExit`` raised
            # at the OUTER yield (e.g. when Starlette closes the SSE
            # response on client disconnect) would tear THIS function down
            # without ever reaching the inner generator's cancel handlers
            # — meaning the partial-content persistence (sub-req 2) would
            # silently miss every real client-disconnect.
            inner = AgentEngineService._run_chat_round_impl(
                db,
                agent_id,
                user_message,
                conversation_id,
                customer_context,
                resume,
                is_disconnected_cb,
                client_message_id,
                last_event_id,
            )
            try:
                async for event in inner:
                    yield event
                span.set_status_ok()
            except Exception as exc:
                span.set_attribute("error.type", type(exc).__name__)
                span.set_status_error(str(exc))
                raise
            finally:
                # No-op when ``inner`` already exhausted; injects
                # ``GeneratorExit`` into a still-paused inner so its
                # ``except (CancelledError, GeneratorExit)`` branch runs
                # (and the shielded ``_persist_incomplete_llm_step``
                # finishes before the request task is reaped).
                await inner.aclose()

    @staticmethod
    async def _run_chat_round_impl(
        db: AsyncSession,
        agent_id: int,
        user_message: str,
        conversation_id: int | None = None,
        customer_context: dict | None = None,
        resume: bool = False,
        is_disconnected_cb: IsDisconnectedCallback | None = None,
        client_message_id: str | None = None,
        last_event_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Execute a chat round and yield SSE-formatted events."""
        # Single SSE emitter for the whole round (sub-req 4). Frames before
        # the lock is acquired (only ``conversation_created``) carry a
        # ``pre-e{n}`` id and skip the buffer; everything after the bind
        # gets a real ``r{round}-e{seq}`` id and is mirrored into the
        # ring buffer for resume.
        emitter = _SSEEmitter()
        # Echo all four correlation ids in the entry log body so your log backend
        # body LIKE search hits the same row regardless of which id the
        # operator / AI agent grabbed first.
        logger.info(
            "── Engine start ── agent_id=%s, conv_id=%s, conversation_external_id=%s, "
            "request_id=%s, trace_id=%s",
            agent_id,
            conversation_id,
            get_conversation_external_id(),
            get_request_id(),
            get_trace_id(),
        )

        agent = await AgentRepository.get_by_id(db, agent_id)
        if not agent:
            raise NotFoundError("Agent not found")

        raw_cfg = agent.engine_config or {}
        config = EngineConfig(**{**EngineConfig().model_dump(), **raw_cfg})
        logger.info(
            "Engine config — model=%s, temperature=%.2f, thinking(first=%s/subsequent=%s), "
            "pre_recall(enabled=%s, tool_id=%s), system_prompt_len=%d",
            config.model.model_name, config.model.temperature,
            config.model.first_round_thinking, config.model.subsequent_rounds_thinking,
            config.pre_recall.enabled, config.pre_recall.tool_id,
            len(config.system_prompt) if config.system_prompt else 0,
        )

        # Create or retrieve conversation
        if conversation_id is None:
            create_data = {
                "tenant_id": agent.tenant_id,
                "agent_id": agent_id,
                "source": "chat",
            }
            if customer_context:
                # Merge customer context into conversation create data
                for key in (
                    "external_user_id", "display_name", "email",
                    "phone", "avatar_url", "source", "title", "metadata",
                ):
                    if key in customer_context and customer_context[key] is not None:
                        create_data[key] = customer_context[key]
            conv = await ConversationRepository.create(db, create_data)
            conversation_id = conv.id
            set_conversation_id(conversation_id)
            set_conversation_external_id(conv.external_id)
            # Backfill the chat_round span: the wrapper opened it before we
            # knew the id (conversation_id was None). Now that the row exists
            # we patch the span attributes so traces are queryable by either
            # the internal id or the user-facing external_id.
            span = current_span()
            span.set_attribute("conversation.id", conversation_id)
            span.set_attribute("conversation.external_id", conv.external_id)
            resume = False  # can't resume a brand-new conversation
            logger.info(
                "Conversation created — conv_id=%s, external_id=%s",
                conversation_id, conv.external_id,
            )
            yield emitter.emit("conversation_created", {
                "conversation_id": conv.id,
                "external_id": conv.external_id,
            })
        else:
            conv = await ConversationRepository.get_by_id(db, conversation_id)
            # Ownership guard: a conversation can only be continued through the
            # same tenant + agent that owns it. Without this, a public channel
            # token (which provides no auth) — or an API key holder targeting
            # a different agent — could pass an arbitrary `conversation_id`
            # and graft user/assistant steps onto someone else's conversation,
            # corrupting their history and bypassing the public-timeline
            # ownership check we just added. Surfaced as 404 (not 403) so the
            # caller can't tell "exists but forbidden" from "missing".
            if (
                conv is None
                or conv.tenant_id != agent.tenant_id
                or conv.agent_id != agent_id
            ):
                if conv is not None:
                    logger.warning(
                        "Conversation ownership mismatch — conv_id=%s "
                        "(tenant=%s, agent=%s) requested via agent=%s tenant=%s",
                        conversation_id, conv.tenant_id, conv.agent_id,
                        agent_id, agent.tenant_id,
                    )
                raise NotFoundError("Conversation not found")
            set_conversation_external_id(conv.external_id)
            current_span().set_attribute(
                "conversation.external_id", conv.external_id
            )
            logger.info(
                "Conversation loaded — conv_id=%s, external_id=%s, rounds=%s",
                conversation_id, conv.external_id, conv.round_count,
            )

        # Sub-req 3: round-level mutual exclusion + idempotency.
        #
        # `_hold_round_lock` blocks (with a wall-clock timeout) until the
        # advisory lock for THIS turn is free, then yields the
        # `(round_number, resume)` pair we should actually use. If we had
        # to wait through an in-flight request committing its round, the
        # yielded values reflect the FRESH `conv.round_count` and any
        # `user_message` that was persisted under our `client_message_id`
        # while we slept — so callers always see the same effective state
        # an observer would see right after the original request finished.
        #
        # We do the auto-resume audit-log + span tagging here (before the
        # long-running body) so resumed turns are searchable in OTel even
        # if the body fails halfway.
        async with _hold_round_lock(
            db, conv, conversation_id, client_message_id,
        ) as (round_number, resume):
            if resume and client_message_id:
                logger.info(
                    "Auto-resume — client_message_id=%s round=%d",
                    client_message_id, round_number,
                )
                current_span().set_attribute("conversation.auto_resume", True)

            round_key = RoundKey(
                conversation_id=conversation_id, round_number=round_number,
            )

            # ── Sub-req 4: Last-Event-ID buffer fast-path ─────────────
            # When a round actually completed and the client only missed
            # the closing tail (e.g. mobile NAT killed the socket as the
            # `done` frame went out), the in-memory ring buffer still
            # has those frames AND `done`. Replay them straight out of
            # RAM — no DB reads, no LLM call, no `assistant_reset` flash.
            # This is the common "I lost the last 200ms" reconnect case.
            #
            # Cold paths (buffer expired, server restarted, multi-process
            # without shared buffer) fall through to the existing step-
            # replay logic below.
            if resume and last_event_id:
                parsed_cursor = parse_event_id(last_event_id)
                last_seq = (
                    parsed_cursor[1]
                    if (parsed_cursor and parsed_cursor[0] == round_number)
                    else -1
                )
                cached = round_event_buffer.slice_after(round_key, last_seq)
                if cached is not None:
                    # Two short-circuit shapes for the buffer fast-path:
                    #
                    #   A. ``cached`` non-empty AND tail contains ``done``
                    #      → client missed the round's closing frames.
                    #      Replay the missing tail; SDK appends and the
                    #      round closes seamlessly.
                    #
                    #   B. ``cached`` empty AND the buffer's last frame
                    #      is terminal (``done`` / ``error``) → client's
                    #      cursor advanced PAST the terminal frame and
                    #      then retried (e.g. SDK persisted the cursor
                    #      to disk, restarted, retried with same cmid;
                    #      or our own SDK's ``onDone`` handler threw and
                    #      bubbled into the retry path). The round is
                    #      DEFINITIVELY finished — re-running the LLM
                    #      would burn tokens and double-bill the user.
                    #      Replay just the terminal frame so the SDK
                    #      sees ``done`` (its handler is idempotent in
                    #      our chat page) and exits the retry loop;
                    #      sending zero frames here would make the SDK
                    #      treat it as an unexpected disconnect and
                    #      retry forever.
                    if cached and any("\nevent: done\n" in raw for raw in cached):
                        logger.info(
                            "Resume FAST-PATH (buffer) — conv=%s round=%s replay=%d events",
                            conversation_id, round_number, len(cached),
                        )
                        current_span().set_attribute(
                            "conversation.resume.path", "buffer_fast",
                        )
                        for raw in cached:
                            yield raw
                        return
                    if not cached:
                        latest = round_event_buffer.latest_raw(round_key)
                        if latest and (
                            "\nevent: done\n" in latest
                            or "\nevent: error\n" in latest
                        ):
                            logger.info(
                                "Resume FAST-PATH (buffer, cursor past terminal) "
                                "— conv=%s round=%s",
                                conversation_id, round_number,
                            )
                            current_span().set_attribute(
                                "conversation.resume.path",
                                "buffer_fast_terminal",
                            )
                            yield latest
                            return

            # All non-fast paths (fresh round, or cold-path resume that
            # WILL regenerate via step-replay) start with a clean buffer.
            # Otherwise a future reconnect could mix old run's frames
            # with this run's, and the client would see duplicated /
            # mismatched ids.
            round_event_buffer.evict(round_key)
            emitter.bind(round_key)
            if resume:
                current_span().set_attribute(
                    "conversation.resume.path",
                    "step_replay" if last_event_id else "step_replay_no_cursor",
                )

            # `round_start` (sub-req 4): one frame sent at the top of
            # every (re)started round. Carries:
            #   - `client_message_id` echo so the client can verify the
            #     server is processing the right turn (defense against
            #     stale request races).
            #   - `watchdog` config so the client adopts server-tuned
            #     timeouts instead of hardcoded ones — thinking models
            #     legitimately need >35s first-chunk windows that the
            #     old hardcoded value would misfire on.
            yield emitter.emit("round_start", {
                "round_number": round_number,
                "resume": resume,
                "client_message_id": client_message_id or None,
                "watchdog": _watchdog_for(config),
            })

            # ── Resume: replay saved steps and rebuild state ──
            resume_tool_round_start = 0
            resume_current_round_messages: list[dict] | None = None
            resume_pending_tool_calls: list[dict] | None = None
            resume_pending_llm_step = None

            if resume:
                saved_steps = await ConversationStepRepository.get_steps_by_round(
                    db, conversation_id, round_number,
                )
                has_user_step = any(s.step_type == "user_message" for s in saved_steps)

                if has_user_step:
                    logger.info("Resume mode — round=%d, saved_steps=%d", round_number, len(saved_steps))

                    # Pre-scan for any incomplete tail so we can emit
                    # ``assistant_reset`` BEFORE replaying the clean steps.
                    #
                    # The original ordering emitted reset AFTER replay,
                    # which broke this exact case: a round that had a few
                    # successful tool rounds + one incomplete trailing
                    # llm_call would replay the clean tool rounds onto
                    # the client's freshly-cleared bubble (via
                    # ``onRoundStart(resume=true)``), then immediately
                    # ``assistant_reset`` wiped them again — leaving the
                    # user staring at only the regenerated tail. The wipe
                    # must precede the content it is wiping ABOUT (the
                    # in-flight partial bubble the client may still be
                    # showing from the dropped connection), not the clean
                    # replay we're about to re-emit.
                    had_incomplete_tail = any(
                        s.step_type == "llm_call" and s.status == "incomplete"
                        for s in saved_steps
                    )
                    if had_incomplete_tail:
                        # ``tool_round`` here is the count of clean (=non-
                        # incomplete) llm_call steps we're about to re-
                        # emit. Lets a future tool_round-aware client
                        # truncate its timeline precisely instead of
                        # nuking everything.
                        clean_llm_count = sum(
                            1 for s in saved_steps
                            if s.step_type == "llm_call" and s.status != "incomplete"
                        )
                        yield emitter.emit("assistant_reset", {
                            "round_number": round_number,
                            "tool_round": clean_llm_count,
                            "reason": "resume_discard_incomplete",
                        })

                    # Rebuild state from saved steps and replay events
                    resume_round_msgs: list[dict] = [{"role": "user", "content": user_message}]
                    llm_round_count = 0

                    for step in saved_steps:
                        if step.step_type == "user_message":
                            user_message = step.content or user_message
                            resume_round_msgs[0] = {"role": "user", "content": user_message}

                        elif step.step_type == "llm_call":
                            # Sub-req 2: skip incomplete llm_call steps. Their
                            # partial content is intentionally discarded — we'll
                            # re-stream a fresh attempt for this tool round.
                            # ``had_incomplete_tail`` was already computed in
                            # the pre-scan above; the reset frame has already
                            # been emitted before replay started.
                            if step.status == "incomplete":
                                logger.info(
                                    "Resume — discarding incomplete llm_call step_id=%s reason=%s",
                                    step.id,
                                    ((step.metadata_ or {}).get("incomplete_reason")
                                     if hasattr(step, "metadata_") else None),
                                )
                                continue
                            llm_round_count += 1
                            # Replay thinking + content
                            if step.thinking_content:
                                yield emitter.emit("thinking_delta", {"content": step.thinking_content})
                            if step.content:
                                yield emitter.emit("content_delta", {"content": step.content})
                            yield emitter.emit("llm_step_created", {"step_id": step.id})

                            if step.response_tool_calls:
                                resume_round_msgs.append({
                                    "role": "assistant",
                                    "content": step.content or None,
                                    "tool_calls": step.response_tool_calls,
                                })
                                resume_pending_llm_step = step

                        elif step.step_type == "tool_call":
                            yield emitter.emit("tool_call", {
                                "step_id": step.id,
                                "tool_name": step.tool_name,
                                "brief": step.brief,
                                "tool_call_id": step.tool_call_id,
                            })
                            yield emitter.emit("tool_result", {
                                "tool_call_id": step.tool_call_id,
                                "result": (step.tool_response or "")[:500],
                            })
                            resume_round_msgs.append({
                                "role": "tool",
                                "tool_call_id": step.tool_call_id,
                                "content": step.tool_response or "",
                            })

                        elif step.step_type == "assistant_message":
                            # Round already complete — just send done and return
                            logger.info("Resume — round already complete, step_id=%s", step.id)
                            yield emitter.emit("done", {
                                "assistant_step_id": step.id,
                                "final_content": step.content or "",
                            })
                            return

                    # Check for pending (un-executed) tool calls from the last LLM step
                    if resume_pending_llm_step and resume_pending_llm_step.response_tool_calls:
                        executed_tc_ids = {
                            s.tool_call_id for s in saved_steps
                            if s.step_type == "tool_call"
                            and s.parent_step_id == resume_pending_llm_step.id
                        }
                        pending = [
                            tc for tc in resume_pending_llm_step.response_tool_calls
                            if tc.get("id") not in executed_tc_ids
                        ]
                        if pending:
                            resume_pending_tool_calls = pending
                            resume_pending_llm_step = resume_pending_llm_step
                        else:
                            resume_pending_llm_step = None

                    resume_current_round_messages = resume_round_msgs
                    resume_tool_round_start = llm_round_count
                    logger.info(
                        "Resume — replayed %d steps, llm_rounds=%d, pending_tools=%d, "
                        "discarded_incomplete=%s",
                        len(saved_steps), llm_round_count,
                        len(resume_pending_tool_calls) if resume_pending_tool_calls else 0,
                        had_incomplete_tail,
                    )
                else:
                    logger.info("Resume requested but no user step found — starting fresh")
                    resume = False

            if not resume:
                logger.info("Round %d begin", round_number)
                # Save user_message step
                user_step = await _create_step(db, conversation_id, agent.tenant_id, {
                    "round_number": round_number,
                    "step_type": "user_message",
                    "content": user_message,
                    # Sub-req 3: persist the idempotency key on the user_message
                    # step so a future retry with the same client_message_id can
                    # be auto-resumed by the lookup at the top of this function.
                    "client_message_id": client_message_id,
                })
                logger.debug("User step saved — step_id=%s", user_step.id)
            else:
                logger.info("Round %d resume", round_number)

            # Auto-set title from first user message
            if not conv.title and user_message:
                await ConversationRepository.update(
                    db, conv, {"title": user_message[:200]}
                )

            # Load tools
            tools_defs = await _load_tools(db, agent_id, config.selected_tool_ids)
            openai_tools = _to_openai_tools(tools_defs) if tools_defs else None
            logger.info("Tools loaded — count=%d, names=%s", len(tools_defs), [t["name"] for t in tools_defs])

            # Build messages
            history = await _build_history(db, conversation_id, config, round_number)
            if resume_current_round_messages is not None:
                current_round_messages = resume_current_round_messages
            else:
                current_round_messages = [{"role": "user", "content": user_message}]
            logger.debug("History built — %d messages from previous rounds", len(history))

            llm_client = create_llm_client()
            model_cfg = config.model

            # Build tool context for executors
            from app.services.tool_executors.base import ToolContext
            tool_ctx = ToolContext(
                db=db,
                conversation_id=conversation_id,
                tenant_id=agent.tenant_id,
                agent_id=agent_id,
            )

            # Built-in datetime variables (Asia/Shanghai)
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            _WEEKDAY_ZH = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
            _now = _dt.now(_tz(_td(hours=8)))
            template_vars: dict[str, str] = {
                "current_date": _now.strftime("%Y-%m-%d"),
                "current_weekday": _WEEKDAY_ZH[_now.weekday()],
                "current_time": _now.strftime("%H:%M"),
                "current_datetime": _now.strftime("%Y-%m-%d %H:%M"),
            }

            # Pre-recall: first round only, when enabled
            if round_number == 1 and config.pre_recall.enabled and config.pre_recall.tool_id:
                import time as _time
                _pr_start = _time.monotonic()
                logger.info(
                    "[Pre-recall] START agent_id=%s conv=%s tool_id=%s query=%r",
                    agent_id, conversation_id, config.pre_recall.tool_id,
                    user_message[:120] if user_message else "",
                )
                pre_recall_result = await _execute_pre_recall(
                    db, agent_id, config.pre_recall.tool_id, user_message, tool_ctx,
                )
                _pr_elapsed = round((_time.monotonic() - _pr_start) * 1000)
                if pre_recall_result:
                    template_vars["first_search"] = pre_recall_result
                    logger.info(
                        "[Pre-recall] DONE  agent_id=%s elapsed=%dms result_chars=%d preview=%r",
                        agent_id, _pr_elapsed, len(pre_recall_result),
                        pre_recall_result[:200],
                    )
                else:
                    logger.info(
                        "[Pre-recall] EMPTY agent_id=%s elapsed=%dms — no results returned",
                        agent_id, _pr_elapsed,
                    )

            rendered_prompt = render_template(config.system_prompt, template_vars) if config.system_prompt else ""
            logger.info(
                "System prompt rendered — template_vars=%s, raw_len=%d, rendered_len=%d",
                list(template_vars.keys()) or "none",
                len(config.system_prompt) if config.system_prompt else 0,
                len(rendered_prompt),
            )

            # Tool loop
            _engine_start_ms = _now_ms()
            _total_llm_ms = 0
            _total_tool_ms = 0
            _total_input_tokens = 0
            _total_output_tokens = 0
            # Stream-level retry bookkeeping (stream-level retry spec): cumulative across all
            # tool rounds in this chat round, surfaced as OTel attributes on the
            # outer `chat_round` span at completion time.
            _round_retry_count_total = 0
            _round_last_incomplete_reason: str | None = None

            # Execute pending tool calls from a resumed interrupted round
            if resume_pending_tool_calls and resume_pending_llm_step:
                logger.info("Executing %d pending tool calls from resume", len(resume_pending_tool_calls))
                for tc in resume_pending_tool_calls:
                    tc_id = tc.get("id", "")
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    args_str = fn.get("arguments", "{}")
                    try:
                        tool_args = json.loads(args_str)
                    except json.JSONDecodeError:
                        tool_args = {}

                    brief = tool_args.get("brief", f"使用工具：{tool_name}")
                    tool_def = next((t for t in tools_defs if t["name"] == tool_name), None)
                    tool_config = tool_def.get("config", {}) if tool_def else {}

                    tool_start = _now_ms()
                    tool_result = await _execute_tool(tool_name, tool_args, tools_defs, tool_ctx)
                    tool_duration = _now_ms() - tool_start
                    _total_tool_ms += tool_duration

                    tool_step = await _create_step(db, conversation_id, agent.tenant_id, {
                        "round_number": round_number,
                        "step_type": "tool_call",
                        "tool_name": tool_name,
                        "tool_type": tool_def.get("tool_type", "") if tool_def else "",
                        "tool_call_id": tc_id,
                        "tool_arguments": tool_args,
                        "tool_response": tool_result,
                        "brief": brief,
                        "duration_ms": tool_duration,
                        "parent_step_id": resume_pending_llm_step.id,
                    })

                    await ConversationRepository.increment_counters(
                        db, conversation_id, tool_call_count=1,
                    )

                    yield emitter.emit("tool_call", {
                        "step_id": tool_step.id,
                        "tool_name": tool_name,
                        "brief": brief,
                        "tool_call_id": tc_id,
                    })
                    yield emitter.emit("tool_result", {
                        "tool_call_id": tc_id,
                        "result": tool_result[:500] if tool_result else "",
                    })

                    current_round_messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": tool_result or "",
                    })

            for tool_round_idx in range(resume_tool_round_start, MAX_TOOL_ROUNDS):
                messages = _assemble_messages(rendered_prompt, history, current_round_messages)

                start_ms = _now_ms()

                # "First-round thinking" is scoped to the very first LLM call of the
                # whole conversation (round_number == 1 AND tool_round_idx == 0).
                # Every other LLM call — whether subsequent tool-loop iterations in
                # round 1 or any call in later rounds — uses `subsequent_rounds_thinking`.
                # This matches the design intent of skipping thinking only to cut
                # the *first-screen* latency, not every round's opening call.
                is_first_screen_call = (round_number == 1 and tool_round_idx == 0)
                thinking_enabled = (
                    model_cfg.first_round_thinking if is_first_screen_call
                    else model_cfg.subsequent_rounds_thinking
                )

                logger.info(
                    "LLM call — round=%d, tool_round=%d, first_screen=%s, thinking=%s, "
                    "model=%s, messages=%d, tools=%s",
                    round_number,
                    tool_round_idx + 1,
                    is_first_screen_call,
                    thinking_enabled,
                    model_cfg.model_name,
                    len(messages),
                    len(openai_tools) if openai_tools else 0,
                )

                # ── Stream-level retry loop (stream-level retry spec) ──
                # We attempt the same `stream_chat` up to LLM_STREAM_RETRY_MAX times
                # whenever the previous attempt ended "incomplete" (timeout / mid-
                # stream error / missing finish_reason). Decisions inside the loop:
                #   - Healthy stream                     → break and continue normally
                #   - LLMAPIError (hard_timeout / API)   → re-raise (engine error path)
                #   - retries disabled / exhausted       → raise LLMAPIError
                #   - client already disconnected        → return silently
                #   - already streamed > RESET_MAX chars → raise (avoid duplicate UX)
                #   - 0 chars shown to user              → silent retry, no SSE event
                #   - 1..RESET_MAX chars shown           → emit `assistant_reset`, retry
                stream_result: LLMStreamResult | None = None
                attempt_retry_count = 0
                attempt_last_reason: str | None = None
                delta_count = 0
                while True:
                    stream_iter, stream_result = await llm_client.stream_chat(
                        messages,
                        model=model_cfg.model_name,
                        tools=openai_tools,
                        temperature=model_cfg.temperature,
                        top_p=model_cfg.top_p,
                        max_tokens=model_cfg.max_tokens,
                        thinking_enabled=thinking_enabled,
                    )

                    partial_content_chars = 0
                    delta_count = 0
                    try:
                        async for delta in stream_iter:
                            delta_count += 1
                            if delta.thinking_content:
                                yield emitter.emit("thinking_delta", {"content": delta.thinking_content})
                            if delta.content:
                                partial_content_chars += len(delta.content)
                                yield emitter.emit("content_delta", {"content": delta.content})
                    except (asyncio.CancelledError, GeneratorExit) as cancel_exc:
                        # Sub-req 2: client closed the SSE connection mid-stream
                        # (TCP RST, browser navigation, mobile WebView background-
                        # kill, …). Without this branch the partial bytes the
                        # user already saw on screen would silently disappear:
                        # `except Exception` doesn't catch CancelledError, and
                        # the round body unwinds before the give_up / api_error
                        # persistence paths can run.
                        #
                        # asyncio.shield protects the DB write from the inbound
                        # cancellation so we can finish the audit row even though
                        # the framework is tearing the task down. We re-raise the
                        # original exception unchanged so FastAPI / starlette see
                        # a normal cancellation (no spurious 500s, no leaked task).
                        if partial_content_chars > 0 or (
                            stream_result is not None and stream_result.thinking_content
                        ):
                            try:
                                await asyncio.shield(_persist_incomplete_llm_step(
                                    db, conversation_id, agent.tenant_id,
                                    round_number=round_number,
                                    stream_result=stream_result,
                                    messages=messages,
                                    openai_tools=openai_tools,
                                    model_cfg=model_cfg,
                                    thinking_enabled=thinking_enabled,
                                    duration_ms=_now_ms() - start_ms,
                                    incomplete_reason="client_cancelled",
                                    retry_count=attempt_retry_count,
                                    partial_content_chars=partial_content_chars,
                                ))
                            except Exception as persist_exc:  # noqa: BLE001
                                logger.warning(
                                    "Failed to persist incomplete step on cancel: %s",
                                    persist_exc,
                                )
                        current_span().set_attribute(
                            "gen_ai.cancel.reason", "client_cancelled",
                        )
                        raise cancel_exc
                    except LLMAPIError as exc:
                        # hard_timeout (or any provider error during streaming) —
                        # NEVER retried in this loop. Tag the chat_round span and
                        # propagate so the router emits `event: error`.
                        attempt_last_reason = exc.error_type or "api_error"
                        current_span().set_attribute(
                            "gen_ai.retry.last_reason", attempt_last_reason,
                        )
                        if attempt_retry_count > 0:
                            current_span().set_attribute(
                                "gen_ai.retry.count", attempt_retry_count,
                            )
                        # Sub-req 2: persist whatever we already streamed so the
                        # user's next refresh / resume can see the partial reply
                        # instead of a phantom empty round. Best-effort — never
                        # fail the request because the audit write failed.
                        if partial_content_chars > 0 or stream_result.thinking_content:
                            try:
                                await _persist_incomplete_llm_step(
                                    db, conversation_id, agent.tenant_id,
                                    round_number=round_number,
                                    stream_result=stream_result,
                                    messages=messages,
                                    openai_tools=openai_tools,
                                    model_cfg=model_cfg,
                                    thinking_enabled=thinking_enabled,
                                    duration_ms=_now_ms() - start_ms,
                                    incomplete_reason=f"api_error:{attempt_last_reason}",
                                    retry_count=attempt_retry_count,
                                    partial_content_chars=partial_content_chars,
                                )
                            except Exception as persist_exc:  # noqa: BLE001
                                logger.warning(
                                    "Failed to persist incomplete step on api_error: %s",
                                    persist_exc,
                                )
                        raise

                    # Healthy stream — break out of the retry loop.
                    if stream_result.incomplete_reason is None:
                        break

                    attempt_last_reason = stream_result.incomplete_reason

                    action = decide_stream_retry_action(
                        partial_content_chars=partial_content_chars,
                        retry_count=attempt_retry_count,
                        retry_enabled=settings.LLM_STREAM_RETRY_ENABLED,
                        retry_max=settings.LLM_STREAM_RETRY_MAX,
                        reset_max_chars=settings.LLM_STREAM_RESET_MAX_CHARS,
                    )
                    if action is StreamRetryAction.GIVE_UP:
                        logger.warning(
                            "LLM stream giving up — round=%d, tool_round=%d, "
                            "reason=%s, retries=%d/%d, partial_chars=%d, enabled=%s",
                            round_number, tool_round_idx + 1, attempt_last_reason,
                            attempt_retry_count, settings.LLM_STREAM_RETRY_MAX,
                            partial_content_chars, settings.LLM_STREAM_RETRY_ENABLED,
                        )
                        # Sub-req 2: persist partial before bubbling the error so
                        # users who refresh see the bytes they already saw on
                        # screen, instead of an empty round.
                        try:
                            await _persist_incomplete_llm_step(
                                db, conversation_id, agent.tenant_id,
                                round_number=round_number,
                                stream_result=stream_result,
                                messages=messages,
                                openai_tools=openai_tools,
                                model_cfg=model_cfg,
                                thinking_enabled=thinking_enabled,
                                duration_ms=_now_ms() - start_ms,
                                incomplete_reason=f"give_up:{attempt_last_reason}",
                                retry_count=attempt_retry_count,
                                partial_content_chars=partial_content_chars,
                            )
                        except Exception as persist_exc:  # noqa: BLE001
                            logger.warning(
                                "Failed to persist incomplete step on give_up: %s",
                                persist_exc,
                            )
                        raise LLMAPIError(
                            status_code=502,
                            message=(
                                f"LLM stream incomplete (reason={attempt_last_reason}, "
                                f"retries={attempt_retry_count}, "
                                f"partial_chars={partial_content_chars})"
                            ),
                            error_type=attempt_last_reason,
                        )

                    # Async-only matrix branch: skip retry if the SSE client is gone.
                    if is_disconnected_cb is not None:
                        try:
                            if await is_disconnected_cb():
                                logger.info(
                                    "LLM stream retry skipped — client disconnected, "
                                    "round=%d, tool_round=%d, reason=%s",
                                    round_number, tool_round_idx + 1, attempt_last_reason,
                                )
                                current_span().set_attribute(
                                    "gen_ai.retry.skipped_reason", "client_disconnected",
                                )
                                # Sub-req 2: persist partial so the user's next
                                # refresh / resume sees what they already saw.
                                try:
                                    await _persist_incomplete_llm_step(
                                        db, conversation_id, agent.tenant_id,
                                        round_number=round_number,
                                        stream_result=stream_result,
                                        messages=messages,
                                        openai_tools=openai_tools,
                                        model_cfg=model_cfg,
                                        thinking_enabled=thinking_enabled,
                                        duration_ms=_now_ms() - start_ms,
                                        incomplete_reason="client_disconnected",
                                        retry_count=attempt_retry_count,
                                        partial_content_chars=partial_content_chars,
                                    )
                                except Exception as persist_exc:  # noqa: BLE001
                                    logger.warning(
                                        "Failed to persist incomplete step on disconnect: %s",
                                        persist_exc,
                                    )
                                return
                        except Exception as exc:  # noqa: BLE001
                            # Disconnect probe should never fail the round.
                            logger.debug(
                                "is_disconnected_cb raised — assuming connected: %s", exc,
                            )

                    # RESET_RETRY: tell the client to wipe the partial bubble before
                    # we restream. SILENT_RETRY needs no SSE event (0 chars shown).
                    if action is StreamRetryAction.RESET_RETRY:
                        yield emitter.emit("assistant_reset", {
                            "round_number": round_number,
                            "tool_round": tool_round_idx + 1,
                            "reason": attempt_last_reason,
                        })

                    attempt_retry_count += 1
                    backoff = min(
                        settings.LLM_STREAM_RETRY_BACKOFF_SEC
                        * (2 ** (attempt_retry_count - 1)),
                        4.0,
                    )
                    logger.info(
                        "LLM stream retrying — round=%d, tool_round=%d, retry=%d/%d, "
                        "reason=%s, partial_chars=%d, backoff=%.2fs",
                        round_number, tool_round_idx + 1, attempt_retry_count,
                        settings.LLM_STREAM_RETRY_MAX, attempt_last_reason,
                        partial_content_chars, backoff,
                    )
                    if backoff > 0:
                        await asyncio.sleep(backoff)

                # Stream ultimately succeeded. Stamp the result for downstream
                # persistence (llm_call step metadata) and tally the chat-round
                # totals so the outer span gets one consolidated retry annotation.
                stream_result.retry_count = attempt_retry_count
                if attempt_retry_count > 0:
                    _round_retry_count_total += attempt_retry_count
                    _round_last_incomplete_reason = attempt_last_reason
                    logger.info(
                        "LLM stream recovered — round=%d, tool_round=%d, retries=%d, "
                        "last_reason=%s",
                        round_number, tool_round_idx + 1, attempt_retry_count,
                        attempt_last_reason,
                    )

                duration_ms = _now_ms() - start_ms
                _total_llm_ms += duration_ms
                _total_input_tokens += stream_result.input_tokens or 0
                _total_output_tokens += stream_result.output_tokens or 0
                logger.info(
                    "LLM response — duration=%dms, tokens(in=%s/out=%s/total=%s), "
                    "finish=%s, tool_calls=%d, deltas=%d",
                    duration_ms,
                    stream_result.input_tokens,
                    stream_result.output_tokens,
                    stream_result.total_tokens,
                    stream_result.finish_reason,
                    len(stream_result.tool_calls) if stream_result.tool_calls else 0,
                    delta_count,
                )
                if stream_result.thinking_content:
                    logger.info(
                        "LLM thinking:\n%s", stream_result.thinking_content,
                    )
                if stream_result.content:
                    logger.info(
                        "LLM content:\n%s", stream_result.content,
                    )
                if stream_result.tool_calls:
                    logger.info(
                        "LLM tool_calls:\n%s",
                        json.dumps(stream_result.tool_calls, ensure_ascii=False, indent=2),
                    )

                # Save LLM call step
                step_metadata: dict = {}
                if attempt_retry_count > 0:
                    # Audit trail for the stream-level retry spec — lets BI count "retry rate" without
                    # having to join against OTel spans.
                    step_metadata["stream_retry_count"] = attempt_retry_count
                    step_metadata["stream_incomplete_reason"] = attempt_last_reason
                llm_step = await _create_step(db, conversation_id, agent.tenant_id, {
                    "round_number": round_number,
                    "step_type": "llm_call",
                    "content": stream_result.content or None,
                    "model_name": stream_result.model or model_cfg.model_name,
                    "provider": "openai_compatible",
                    "thinking_enabled": thinking_enabled,
                    "thinking_content": stream_result.thinking_content or None,
                    "request_messages": messages,
                    "request_tools": openai_tools,
                    "request_params": {
                        "temperature": model_cfg.temperature,
                        "top_p": model_cfg.top_p,
                        "max_tokens": model_cfg.max_tokens,
                    },
                    "response_tool_calls": stream_result.tool_calls or None,
                    "finish_reason": stream_result.finish_reason,
                    "request_id": stream_result.request_id,
                    "input_tokens": stream_result.input_tokens,
                    "output_tokens": stream_result.output_tokens,
                    "total_tokens": stream_result.total_tokens,
                    "duration_ms": duration_ms,
                    "metadata": step_metadata,
                })
                logger.debug("LLM step saved — step_id=%s", llm_step.id)

                # Update conversation token counters
                await ConversationRepository.increment_counters(
                    db, conversation_id,
                    llm_call_count=1,
                    input_tokens=stream_result.input_tokens,
                    output_tokens=stream_result.output_tokens,
                    total_tokens=stream_result.total_tokens,
                )

                yield emitter.emit("llm_step_created", {"step_id": llm_step.id})

                # If LLM wants to call tools
                if stream_result.tool_calls:
                    logger.info(
                        "Tool calls requested — %s",
                        [tc.get("function", {}).get("name") for tc in stream_result.tool_calls],
                    )
                    assistant_msg = {
                        "role": "assistant",
                        "content": stream_result.content or None,
                        "tool_calls": stream_result.tool_calls,
                    }
                    current_round_messages.append(assistant_msg)

                    for tc in stream_result.tool_calls:
                        tc_id = tc.get("id", "")
                        fn = tc.get("function", {})
                        tool_name = fn.get("name", "")
                        args_str = fn.get("arguments", "{}")
                        try:
                            tool_args = json.loads(args_str)
                        except json.JSONDecodeError:
                            tool_args = {}

                        brief = tool_args.get("brief", f"使用工具：{tool_name}")
                        tool_def = next((t for t in tools_defs if t["name"] == tool_name), None)
                        tool_id = tool_def["id"] if tool_def else "?"

                        tool_config = tool_def.get("config", {}) if tool_def else {}

                        logger.info(
                            "Executing tool — name=%s, call_id=%s, agent_id=%s, tool_id=%s\n"
                            "  ▶ POST /api/v1/agents/%s/tools/%s/execute\n"
                            "  ▶ config:\n%s\n"
                            "  ▶ args:\n%s",
                            tool_name, tc_id, agent_id, tool_id,
                            agent_id, tool_id,
                            json.dumps(tool_config, ensure_ascii=False, indent=2),
                            json.dumps(tool_args, ensure_ascii=False, indent=2),
                        )
                        tool_start = _now_ms()

                        # Execute tool
                        tool_result = await _execute_tool(tool_name, tool_args, tools_defs, tool_ctx)

                        tool_duration = _now_ms() - tool_start
                        _total_tool_ms += tool_duration
                        logger.info(
                            "Tool executed — name=%s, duration=%dms, result_len=%d\n  ◀ response:\n%s",
                            tool_name, tool_duration, len(tool_result) if tool_result else 0,
                            tool_result,
                        )

                        # Save tool_call step
                        tool_step = await _create_step(db, conversation_id, agent.tenant_id, {
                            "round_number": round_number,
                            "step_type": "tool_call",
                            "tool_name": tool_name,
                            "tool_type": tool_def.get("tool_type", "") if tool_def else "",
                            "tool_call_id": tc_id,
                            "tool_arguments": tool_args,
                            "tool_response": tool_result,
                            "brief": brief,
                            "duration_ms": tool_duration,
                            "parent_step_id": llm_step.id,
                        })

                        await ConversationRepository.increment_counters(
                            db, conversation_id, tool_call_count=1,
                        )

                        yield emitter.emit("tool_call", {
                            "step_id": tool_step.id,
                            "tool_name": tool_name,
                            "brief": brief,
                            "tool_call_id": tc_id,
                        })

                        yield emitter.emit("tool_result", {
                            "tool_call_id": tc_id,
                            "result": tool_result[:500] if tool_result else "",
                        })

                        current_round_messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": tool_result or "",
                        })

                    # Continue to next LLM call
                    continue

                # No tool calls — LLM produced final answer
                # Surface stream-level retry totals on the outer chat_round span so
                # ops can compute "rounds with ≥1 retry / total rounds" trivially.
                if _round_retry_count_total > 0:
                    current_span().set_attribute(
                        "gen_ai.retry.count", _round_retry_count_total,
                    )
                    current_span().set_attribute(
                        "gen_ai.retry.last_reason", _round_last_incomplete_reason or "",
                    )
                    current_span().set_attribute("gen_ai.stream.incomplete", True)
                if stream_result.content:
                    assistant_step = await _create_step(db, conversation_id, agent.tenant_id, {
                        "round_number": round_number,
                        "step_type": "assistant_message",
                        "content": stream_result.content,
                        "parent_step_id": llm_step.id,
                    })

                    await ConversationRepository.increment_counters(
                        db, conversation_id, round_count=1,
                    )

                    _engine_total_ms = _now_ms() - _engine_start_ms
                    logger.info(
                        "── Engine done ── conv_id=%s, round=%d, content_len=%d, "
                        "llm_rounds=%d, total=%dms(llm=%dms+tool=%dms), "
                        "tokens(in=%d/out=%d), retries=%d",
                        conversation_id, round_number, len(stream_result.content),
                        tool_round_idx + 1, _engine_total_ms, _total_llm_ms, _total_tool_ms,
                        _total_input_tokens, _total_output_tokens, _round_retry_count_total,
                    )
                    yield emitter.emit("done", {
                        "assistant_step_id": assistant_step.id,
                        "final_content": stream_result.content,
                    })
                else:
                    _engine_total_ms = _now_ms() - _engine_start_ms
                    logger.info(
                        "── Engine done ── conv_id=%s, round=%d, empty response, "
                        "total=%dms, retries=%d",
                        conversation_id, round_number, _engine_total_ms,
                        _round_retry_count_total,
                    )
                    yield emitter.emit("done", {"assistant_step_id": None, "final_content": ""})
                return

            # Exceeded max tool rounds
            logger.warning("── Engine abort ── exceeded max tool rounds (%d)", MAX_TOOL_ROUNDS)
            yield emitter.emit("error", {"message": "Exceeded maximum tool call rounds"})


# ── Helper functions ──

def _watchdog_for(config: EngineConfig) -> dict:
    """Return per-round watchdog config the SSE client should adopt.

    Values are deliberately conservative for thinking models: r1 / Qwen
    QwQ etc. legitimately spend 60–120 seconds on the first token while
    the chain-of-thought builds up, and the old hardcoded 35s on the
    client tripped on every one of them. We trade a slightly slower
    "obviously hung" detection for fewer false-positive timeouts on
    legitimate slow rounds — the overall wall-clock cap still bounds
    catastrophic hangs.

    Hardcoded for now; promoting these to ``EngineConfig`` columns is a
    follow-up when we want per-agent overrides.
    """
    thinking = bool(
        config.model.first_round_thinking
        or config.model.subsequent_rounds_thinking
    )
    if thinking:
        return {
            "first_chunk_ms": 90_000,
            "chunk_idle_ms": 30_000,
            "overall_ms": 300_000,
        }
    return {
        "first_chunk_ms": 35_000,
        "chunk_idle_ms": 15_000,
        "overall_ms": 240_000,
    }


def _sse(event: str, data: dict, *, event_id: str | None = None) -> str:
    """Format one SSE frame.

    ``event_id`` is the resume cursor (sub-req 4): every frame the engine
    yields under a round carries one, written ahead of ``event:`` so the
    receiver-side parser sees it before the type. The router-emitted
    terminal ``error`` frames don't go through here and don't carry an id
    (they end the stream — there's nothing to resume).
    """
    head = f"id: {event_id}\n" if event_id else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class _SSEEmitter:
    """Single source of truth for outbound SSE frames within a round.

    Two responsibilities, deliberately on the same object so they can't
    drift apart:

    1. **Stamp every frame with a monotonic event id** in the format
       ``r{round}-e{seq}``. Pre-round frames (``conversation_created``)
       use ``pre-e{seq}`` and are NOT buffered — they're never replayed
       on reconnect because the conversation id is already in the
       client's state by then.
    2. **Mirror each frame into the in-memory ring buffer** so a same-
       turn reconnect with ``last_event_id`` can replay the missing
       tail without touching the DB.

    The buffer write happens BEFORE the frame is yielded so a crashing
    yield (cancellation between buffer write and network flush) doesn't
    leave the buffer ahead of what was actually sent. In the worst case
    we replay one extra frame to the new connection — much better than
    dropping it.
    """

    __slots__ = ("_round_key", "_seq", "_seq_offset")

    def __init__(self) -> None:
        self._round_key: RoundKey | None = None
        # Pre-round seq counter (negative-prefixed in ids so they can't be
        # confused with round-scoped ids).
        self._seq: int = 0
        self._seq_offset: int = 0

    def bind(self, round_key: RoundKey, *, seq_offset: int = 0) -> None:
        """Attach the emitter to a specific round.

        ``seq_offset`` lets the engine resume the seq counter past
        events that were already buffered by a previous request on this
        round (so a retry's new emissions don't collide with the
        cached ones).
        """
        self._round_key = round_key
        self._seq = seq_offset
        self._seq_offset = seq_offset

    @property
    def next_seq(self) -> int:
        return self._seq

    def emit(self, event: str, data: dict) -> str:
        seq = self._seq
        self._seq += 1
        if self._round_key is None:
            event_id = f"pre-e{seq}"
            return _sse(event, data, event_id=event_id)
        event_id = format_event_id(self._round_key.round_number, seq)
        raw = _sse(event, data, event_id=event_id)
        round_event_buffer.append(self._round_key, seq, raw)
        return raw


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _create_step(
    db: AsyncSession,
    conversation_id: int,
    tenant_id: str,
    data: dict,
):
    """Create a conversation step with auto-incrementing step_order."""
    max_order = await ConversationStepRepository.get_max_step_order(db, conversation_id)
    data["conversation_id"] = conversation_id
    data["tenant_id"] = tenant_id
    data["step_order"] = max_order + 1
    if "metadata" not in data:
        data["metadata"] = {}
    return await ConversationStepRepository.create(db, data)


async def _persist_incomplete_llm_step(
    db: AsyncSession,
    conversation_id: int,
    tenant_id: str,
    *,
    round_number: int,
    stream_result,
    messages: list[dict],
    openai_tools,
    model_cfg,
    thinking_enabled: bool,
    duration_ms: int,
    incomplete_reason: str,
    retry_count: int,
    partial_content_chars: int,
):
    """Persist a partial llm_call step that was streamed to the user but never
    finished cleanly (sub-req 2 / design 3.3 weak-network).

    Marks ``status='incomplete'`` so:
        - public timeline filters it out (no "phantom round" on refresh)
        - resume branch discards + emits assistant_reset before regenerating
        - admin/log timeline still surfaces it for ops debugging
        - history builder skips it when assembling messages for next rounds

    Conversation counters are intentionally NOT incremented here — the eventual
    successful retry's llm_call (or the absence thereof if the user gives up)
    is the source of truth for `llm_call_count` / token tallies.
    """
    metadata = {
        "incomplete_reason": incomplete_reason,
        "partial_content_chars": partial_content_chars,
    }
    if retry_count > 0:
        metadata["stream_retry_count"] = retry_count

    return await _create_step(db, conversation_id, tenant_id, {
        "round_number": round_number,
        "step_type": "llm_call",
        "content": stream_result.content or None,
        "model_name": (stream_result.model or model_cfg.model_name) if stream_result else model_cfg.model_name,
        "provider": "openai_compatible",
        "thinking_enabled": thinking_enabled,
        "thinking_content": stream_result.thinking_content or None,
        "request_messages": messages,
        "request_tools": openai_tools,
        "request_params": {
            "temperature": model_cfg.temperature,
            "top_p": model_cfg.top_p,
            "max_tokens": model_cfg.max_tokens,
        },
        "response_tool_calls": stream_result.tool_calls or None,
        "finish_reason": stream_result.finish_reason,
        "request_id": stream_result.request_id,
        "input_tokens": stream_result.input_tokens or None,
        "output_tokens": stream_result.output_tokens or None,
        "total_tokens": stream_result.total_tokens or None,
        "duration_ms": duration_ms,
        "status": "incomplete",
        "metadata": metadata,
    })


async def _load_tools(db: AsyncSession, agent_id: int, selected_ids: list[int]) -> list[dict]:
    """Load enabled tools for the agent, filtered by selected_tool_ids.

    Returns dicts with id, name, description, parameters_schema, tool_type, config.
    """
    if not selected_ids:
        return []
    tools = await AgentToolRepository.get_by_agent_id(db, agent_id)
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description or "",
            "parameters_schema": t.parameters_schema,
            "tool_type": t.tool_type,
            "config": t.config or {},
        }
        for t in tools
        if t.id in selected_ids and t.is_enabled
    ]


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert internal tool definitions to OpenAI function calling format."""
    result = []
    for t in tools:
        schema = t.get("parameters_schema") or {"type": "object", "properties": {}}
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": _sanitize_schema(schema),
            },
        })
    return result


_OPENAI_FORBIDDEN_TOP_KEYS = {"oneOf", "anyOf", "allOf", "enum", "not"}


def _sanitize_schema(schema: dict) -> dict:
    """Strip top-level keys that OpenAI function calling forbids (anyOf, oneOf, etc.).

    When `anyOf` contains `required` constraints, merge them into optional
    fields so the intent is preserved without violating the API spec.
    """
    forbidden = _OPENAI_FORBIDDEN_TOP_KEYS & schema.keys()
    if not forbidden:
        return schema

    cleaned = {k: v for k, v in schema.items() if k not in _OPENAI_FORBIDDEN_TOP_KEYS}
    logger.warning(
        "Stripped forbidden top-level keys %s from tool schema, original keys: %s",
        forbidden, list(schema.keys()),
    )
    return cleaned


async def _build_history(
    db: AsyncSession,
    conversation_id: int,
    config: EngineConfig,
    current_round: int,
) -> list[dict]:
    """Build history messages from past rounds based on context config."""
    if current_round <= 1:
        return []

    steps = await ConversationStepRepository.get_history_steps(db, conversation_id)
    if not steps:
        return []

    # Group steps by round
    rounds: dict[int, list] = {}
    for s in steps:
        rn = s["round_number"]
        if rn >= current_round:
            continue
        rounds.setdefault(rn, []).append(s)

    sorted_round_nums = sorted(rounds.keys())

    # Apply max_rounds limit
    max_rounds = config.context.max_rounds
    if max_rounds > 0 and len(sorted_round_nums) > max_rounds:
        sorted_round_nums = sorted_round_nums[-max_rounds:]

    history_tool_rounds = config.context.history_tool_rounds
    tool_eligible_rounds = set()
    if history_tool_rounds > 0:
        tool_eligible_rounds = set(sorted_round_nums[-history_tool_rounds:])

    messages: list[dict] = []
    for rn in sorted_round_nums:
        round_steps = sorted(rounds[rn], key=lambda s: s["step_order"])
        include_tools = rn in tool_eligible_rounds

        for s in round_steps:
            # Sub-req 2: incomplete llm_call steps preserve partial content for
            # ops/audit but must NOT be replayed into next-round LLM context —
            # their tool_calls / content can be malformed.
            if s.get("status") == "incomplete":
                continue
            st = s["step_type"]
            if st == "user_message" and s.get("content"):
                messages.append({"role": "user", "content": s["content"]})
            elif st == "assistant_message" and s.get("content"):
                messages.append({"role": "assistant", "content": s["content"]})
            elif include_tools and st == "llm_call" and s.get("response_tool_calls"):
                messages.append({
                    "role": "assistant",
                    "content": s.get("content") or None,
                    "tool_calls": s["response_tool_calls"],
                })
            elif include_tools and st == "tool_call" and s.get("tool_call_id"):
                messages.append({
                    "role": "tool",
                    "tool_call_id": s["tool_call_id"],
                    "content": s.get("tool_response") or "",
                })

    return messages


def _assemble_messages(
    system_prompt: str,
    history: list[dict],
    current_round: list[dict],
) -> list[dict]:
    """Assemble the full messages array for an LLM call."""
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)
    messages.extend(current_round)
    return messages


async def _execute_pre_recall(
    db: AsyncSession,
    agent_id: int,
    tool_id: int,
    query: str,
    ctx: "ToolContext",
) -> str:
    """Execute pre-recall search using the configured search tool instance."""
    try:
        tool = await AgentToolRepository.get_by_id(db, tool_id)
        if not tool or not tool.is_enabled or tool.tool_type != "search":
            logger.warning(
                "[Pre-recall] tool_id=%s skipped — found=%s enabled=%s type=%s",
                tool_id, tool is not None,
                getattr(tool, "is_enabled", None),
                getattr(tool, "tool_type", None),
            )
            return ""

        logger.info(
            "[Pre-recall] executing tool name=%r type=%s config_keys=%s",
            tool.name, tool.tool_type, list((tool.config or {}).keys()),
        )

        from app.services.tool_executors import execute_tool as _dispatch
        result = await _dispatch(
            tool.name, tool.tool_type,
            {"query": query}, tool.config or {}, ctx,
        )
        if not result or "<result " not in result:
            return ""
        return result
    except Exception as exc:
        logger.warning("[Pre-recall] FAILED (non-fatal): %s", exc, exc_info=True)
        return ""


async def _execute_tool(
    tool_name: str,
    tool_args: dict,
    tools_defs: list[dict],
    ctx: "ToolContext",
) -> str:
    """Dispatch tool execution to the appropriate executor based on tool_type."""
    from app.services.tool_executors import execute_tool as _dispatch

    tool_def = next((t for t in tools_defs if t["name"] == tool_name), None)
    if tool_def is None:
        logger.warning("Tool definition not found for name=%s", tool_name)
        return f"Error: tool '{tool_name}' not found."

    tool_type = tool_def.get("tool_type", "")
    config = tool_def.get("config", {})

    return await _dispatch(tool_name, tool_type, tool_args, config, ctx)
