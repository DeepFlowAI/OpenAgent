"""
Sync router — trigger sync & parse for a knowledge base.
"""
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db
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
    db: AsyncSession = Depends(get_db),
):
    """Trigger git sync and document parsing for a knowledge base."""
    force_full = body is not None and body.sync_mode == SyncMode.full
    result = await SyncService.sync_and_parse(db, kb_id, force_full=force_full)
    return result
