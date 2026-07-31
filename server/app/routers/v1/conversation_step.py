"""
ConversationStep router — execution log query and write APIs
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import (
    AuthContext,
    get_db,
    require_admin_session_or_scope,
    require_agent_access,
    require_api_key_scope,
)
from app.schemas.conversation_step import (
    ConversationTimelineResponse,
    StepDetailResponse,
    StepCreate,
    StepFeedbackResponse,
    StepFeedbackSubmit,
    StepUpdate,
)
from app.services.conversation_step_service import ConversationStepService
from app.services.conversation_service import ConversationService
from app.core.exceptions import NotFoundError

router = APIRouter(
    prefix="/agents/{agent_id}/conversations/{conversation_id}/steps",
    tags=["ConversationSteps"],
)


@router.get("", response_model=ConversationTimelineResponse)
async def get_conversation_timeline(
    agent_id: int,
    conversation_id: int,
    auth: AuthContext = Depends(require_agent_access("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Get conversation execution timeline (lightweight, for log page)"""
    conversation = await ConversationService.get_by_id(db, conversation_id)
    if (
        conversation["tenant_id"] != auth.tenant_id
        or conversation["agent_id"] != agent_id
    ):
        raise NotFoundError("Conversation not found")
    return await ConversationStepService.get_timeline(db, conversation_id)


@router.get("/{step_id}", response_model=StepDetailResponse)
async def get_step_detail(
    agent_id: int,
    conversation_id: int,
    step_id: int,
    auth: AuthContext = Depends(require_agent_access("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Get full step detail (for LLM request/response modal)"""
    conversation = await ConversationService.get_by_id(db, conversation_id)
    if (
        conversation["tenant_id"] != auth.tenant_id
        or conversation["agent_id"] != agent_id
    ):
        raise NotFoundError("Conversation not found")
    step = await ConversationStepService.get_step_detail(db, step_id)
    step_conversation_id = (
        step.get("conversation_id")
        if isinstance(step, dict)
        else step.conversation_id
    )
    if step_conversation_id != conversation_id:
        raise NotFoundError("Step not found")
    return step


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
    auth: AuthContext = Depends(require_admin_session_or_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Add a step to a conversation (used by agent engine)"""
    return await ConversationStepService.create_step(
        db, conversation_id, auth.tenant_id, body
    )


@router.put("/{step_id}", response_model=StepDetailResponse)
async def update_step(
    agent_id: int,
    conversation_id: int,
    step_id: int,
    body: StepUpdate,
    auth: AuthContext = Depends(require_admin_session_or_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing step (e.g. when LLM response arrives)"""
    return await ConversationStepService.update_step(
        db, step_id, conversation_id, body
    )
