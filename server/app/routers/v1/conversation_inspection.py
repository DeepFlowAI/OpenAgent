"""Human quality-workbench APIs."""
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.deps import AuthContext, get_db, require_agent_access
from app.schemas.conversation_inspection import InspectionResponse, InspectionSave, QualityQueueResponse
from app.services.conversation_inspection_service import ConversationInspectionService

router = APIRouter(prefix="/agents/{agent_id}/quality", tags=["Conversation quality"])

@router.get("/conversations", response_model=QualityQueueResponse)
async def get_quality_queue(agent_id: int, auth: AuthContext = Depends(require_agent_access("chat")), start_time: datetime | None = None, end_time: datetime | None = None, source: str | None = None, channel_id: str | None = None, channel_source: str | None = None, message_content: str | None = None, conversation_id: str | None = None, external_user_id: str | None = None, inspection_status: str | None = None, inspection_tag: str | None = None, db: AsyncSession = Depends(get_db)):
    """Return a stable, newest-first quality queue for the supplied filters."""
    return await ConversationInspectionService.get_queue(db, auth.tenant_id, agent_id, start_time=start_time, end_time=end_time, source=source, channel_id=channel_id, channel_source=channel_source, message_content=message_content, conversation_id=conversation_id, external_user_id=external_user_id, inspection_status=inspection_status, inspection_tag=inspection_tag)

@router.post("/conversations/{conversation_id}/steps/{step_id}", response_model=InspectionResponse)
async def save_inspection(agent_id: int, conversation_id: int, step_id: int, body: InspectionSave, auth: AuthContext = Depends(require_agent_access("chat")), db: AsyncSession = Depends(get_db)):
    """Create or overwrite one human quality inspection."""
    return await ConversationInspectionService.save(db, tenant_id=auth.tenant_id, agent_id=agent_id, conversation_id=conversation_id, step_id=step_id, inspector_id=auth.account_id, data=body)
