"""
Conversation router — conversation list and detail APIs
"""
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_scope
from app.core.exceptions import NotFoundError
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
)
from app.services.conversation_service import ConversationService

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
        conversation_id=conversation_id,
        external_user_id=external_user_id,
        search=search,
    )


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
