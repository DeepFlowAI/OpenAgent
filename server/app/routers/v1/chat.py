"""
Chat router — SSE streaming chat endpoint for agent testing.
"""
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.trace import (
    set_conversation_external_id,
    set_request_id,
    set_trace_id,
)
from app.db.deps import get_db, require_scope
from app.routers.v1.sse import with_sse_heartbeat
from app.schemas.chat import ChatRequest
from app.services.agent_engine_service import AgentEngineService
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/{agent_id}/chat", tags=["Chat"])


@router.post("")
async def chat(
    agent_id: int,
    body: ChatRequest,
    request: Request,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """SSE streaming chat with an agent.

    Creates a new conversation (or continues existing one) and streams
    thinking, content, tool calls, and the final response as SSE events.
    """
    agent = await AgentService.get_by_id(db, agent_id)
    if agent.tenant_id != tenant_id:
        raise NotFoundError("Agent not found")

    trace_id = set_trace_id()
    # Echo client-supplied correlation ids into the request log context so
    # they show up as searchable log_attributes AND inside the body of the
    # entry log line (handy for body LIKE search via your log backend MCP).
    set_request_id(body.request_id)
    if body.conversation_external_id:
        set_conversation_external_id(body.conversation_external_id)
    logger.info(
        "Chat request received — agent_id=%s, conversation_id=%s, "
        "conversation_external_id=%s, request_id=%s, trace_id=%s, msg_len=%d",
        agent_id,
        body.conversation_id,
        body.conversation_external_id or "-",
        body.request_id or "-",
        trace_id,
        len(body.message),
    )

    async def event_generator():
        try:
            stream = AgentEngineService.run_chat_round(
                db,
                agent_id=agent_id,
                user_message=body.message,
                conversation_id=body.conversation_id,
                customer_context=body.customer_context.model_dump(exclude_none=True) if body.customer_context else None,
                resume=body.resume,
                # Engine polls this between LLM stream attempts so we don't burn
                # tokens retrying for a client that already closed the SSE.
                is_disconnected_cb=request.is_disconnected,
                client_message_id=body.client_message_id,
                last_event_id=body.last_event_id,
            )
            async for event in with_sse_heartbeat(stream):
                yield event
        except Exception as e:
            logger.exception("Chat stream error")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            logger.info("Chat stream ended")

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
