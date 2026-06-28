"""
ConversationStep router — execution log query and write APIs
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_api_key_scope, require_scope
from app.schemas.conversation_step import (
    ConversationTimelineResponse,
    StepDetailResponse,
    StepCreate,
    StepFeedbackResponse,
    StepFeedbackSubmit,
    StepUpdate,
)
from app.services.conversation_step_service import ConversationStepService

router = APIRouter(
    prefix="/agents/{agent_id}/conversations/{conversation_id}/steps",
    tags=["ConversationSteps"],
)


@router.get("", response_model=ConversationTimelineResponse)
async def get_conversation_timeline(
    agent_id: int,
    conversation_id: int,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Get conversation execution timeline (lightweight, for log page)"""
    return await ConversationStepService.get_timeline(db, conversation_id)


@router.get("/{step_id}", response_model=StepDetailResponse)
async def get_step_detail(
    agent_id: int,
    conversation_id: int,
    step_id: int,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Get full step detail (for LLM request/response modal)"""
    return await ConversationStepService.get_step_detail(db, step_id)


@router.post("/{step_id}/feedback", response_model=StepFeedbackResponse)
async def submit_step_feedback(
    agent_id: int,
    conversation_id: int,
    step_id: int,
    body: StepFeedbackSubmit,
    tenant_id: str = Depends(require_api_key_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Submit or overwrite API caller feedback for one assistant reply step."""
    return await ConversationStepService.submit_api_feedback(
        db,
        tenant_id=tenant_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        step_id=step_id,
        data=body,
    )


@router.post(
    "",
    response_model=StepDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_step(
    agent_id: int,
    conversation_id: int,
    body: StepCreate,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Add a step to a conversation (used by agent engine)"""
    return await ConversationStepService.create_step(
        db, conversation_id, tenant_id, body
    )


@router.put("/{step_id}", response_model=StepDetailResponse)
async def update_step(
    agent_id: int,
    conversation_id: int,
    step_id: int,
    body: StepUpdate,
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing step (e.g. when LLM response arrives)"""
    return await ConversationStepService.update_step(
        db, step_id, conversation_id, body
    )
