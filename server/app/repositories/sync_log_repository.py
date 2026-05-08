"""
SyncLog repository
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_log import SyncLog


def _sync_log_mappable_keys() -> frozenset[str]:
    """Column keys only — avoids hasattr() lazy-load in async ORM."""
    return frozenset(SyncLog.__mapper__.columns.keys())


_MAPPABLE = _sync_log_mappable_keys()


class SyncLogRepository:

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SyncLog:
        item = SyncLog(**data)
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def get_by_id(db: AsyncSession, log_id: int) -> SyncLog | None:
        return await db.get(SyncLog, log_id)

    @staticmethod
    async def update(db: AsyncSession, item: SyncLog, data: dict) -> SyncLog:
        for key, value in data.items():
            if key in _MAPPABLE:
                setattr(item, key, value)
        await db.flush()
        return item

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        kb_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[SyncLog], int]:
        base_filter = (SyncLog.knowledge_base_id == kb_id,)

        total_result = await db.execute(
            select(func.count()).select_from(SyncLog).where(*base_filter)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(SyncLog)
            .where(*base_filter)
            .order_by(SyncLog.started_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total
