"""
Sync router — trigger sync & parse for a knowledge base.
"""
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.deps import AuthContext, get_db, require_admin_session_or_scope
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.services.sync_service import SyncService

router = APIRouter(prefix="/knowledge-bases", tags=["Sync"])


class SyncMode(str, Enum):
    auto = "auto"
    full = "full"


class TriggerSyncRequest(BaseModel):
    sync_mode: SyncMode = SyncMode.auto


@router.post("/{kb_id}/sync", status_code=status.HTTP_200_OK)
async def trigger_sync(
    kb_id: int,
    body: Optional[TriggerSyncRequest] = None,
    auth: AuthContext = Depends(require_admin_session_or_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger git sync and document parsing for a knowledge base."""
    knowledge_base = await KnowledgeBaseRepository.get_by_id(db, kb_id)
    if (
        not knowledge_base
        or knowledge_base.status == "deleted"
        or knowledge_base.tenant_id != auth.tenant_id
    ):
        raise NotFoundError("Knowledge base not found")
    force_full = body is not None and body.sync_mode == SyncMode.full
    return await SyncService.start_sync(db, kb_id, force_full=force_full)


@router.post("/{kb_id}/sync/cancel", status_code=status.HTTP_200_OK)
async def cancel_sync(
    kb_id: int,
    sync_log_id: int | None = Query(default=None),
    auth: AuthContext = Depends(require_admin_session_or_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Stop a running sync job or clear an orphaned running log."""
    knowledge_base = await KnowledgeBaseRepository.get_by_id(db, kb_id)
    if (
        not knowledge_base
        or knowledge_base.status == "deleted"
        or knowledge_base.tenant_id != auth.tenant_id
    ):
        raise NotFoundError("Knowledge base not found")
    return await SyncService.cancel_sync(
        db, kb_id, sync_log_id=sync_log_id,
    )
