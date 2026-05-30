"""
Conversation router — conversation list and detail APIs
"""
from datetime import datetime, timezone
import json
import logging

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_scope
from app.core.exceptions import NotFoundError
from app.routers.v1.sse import with_sse_heartbeat
from app.schemas.channel import ChannelOptionListResponse
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
)
from app.schemas.conversation_step import ToolResultSubmit
from app.services.agent_engine_service import AgentEngineService
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/{agent_id}/conversations", tags=["Conversations"]
)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    agent_id: int,
    tenant_id: str = Depends(require_scope("chat")),
    page: int = 1,
    per_page: int = 10,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    status_filter: str | None = None,
    source: str | None = None,
    channel_id: str | None = None,
    channel_source: str | None = None,
    message_content: str | None = None,
    conversation_id: str | None = None,
    external_user_id: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List conversations for an agent with filtering and pagination"""
    return await ConversationService.get_paginated(
        db,
        tenant_id,
        agent_id,
        page=page,
        per_page=per_page,
        start_time=start_time,
        end_time=end_time,
        status=status_filter,
        source=source,
        channel_id=channel_id,
        channel_source=channel_source,
        message_content=message_content,
        conversation_id=conversation_id,
        external_user_id=external_user_id,
        search=search,
    )


@router.get("/export")
async def export_conversations(
    agent_id: int,
    tenant_id: str = Depends(require_scope("chat")),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    status_filter: str | None = None,
    source: str | None = None,
    channel_id: str | None = None,
    channel_source: str | None = None,
    message_content: str | None = None,
    conversation_id: str | None = None,
    external_user_id: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Export all filtered conversation messages as CSV."""
    csv_content = await ConversationService.export_messages_csv(
        db,
        tenant_id,
        agent_id,
        start_time=start_time,
        end_time=end_time,
        status=status_filter,
        source=source,
        channel_id=channel_id,
        channel_source=channel_source,
        message_content=message_content,
        conversation_id=conversation_id,
        external_user_id=external_user_id,
        search=search,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"conversations-{agent_id}-{timestamp}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/channel-options", response_model=ChannelOptionListResponse)
async def list_conversation_channel_options(
    agent_id: int,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """List Web SDK channel options bound to the current agent."""
    return await ConversationService.get_channel_options(db, tenant_id, agent_id)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    agent_id: int,
    conversation_id: int,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Get conversation detail by ID"""
    conv = await ConversationService.get_by_id(db, conversation_id)
    if conv["tenant_id"] != tenant_id:
        raise NotFoundError("Conversation not found")
    return conv


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    agent_id: int,
    body: ConversationCreate,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation"""
    body.tenant_id = tenant_id
    return await ConversationService.create(db, body)


@router.post("/{conversation_id}/end", response_model=ConversationResponse)
async def end_conversation(
    agent_id: int,
    conversation_id: int,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Mark a conversation as ended"""
    conv = await ConversationService.get_by_id(db, conversation_id)
    if conv["tenant_id"] != tenant_id:
        raise NotFoundError("Conversation not found")
    return await ConversationService.end_conversation(db, conversation_id)


@router.post("/{conversation_id}/tool-results")
async def submit_tool_result(
    agent_id: int,
    conversation_id: int,
    body: ToolResultSubmit,
    request: Request,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Submit the external result for a pending tool call."""
    async def event_generator():
        try:
            stream = AgentEngineService.submit_tool_result_stream(
                db,
                agent_id=agent_id,
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                data=body,
                is_disconnected_cb=request.is_disconnected,
            )
            async for event in with_sse_heartbeat(stream):
                yield event
        except Exception as exc:
            logger.exception("Tool result stream error")
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
