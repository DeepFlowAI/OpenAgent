"""
KnowledgeBase repository
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase


class KnowledgeBaseRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, kb_id: int) -> KnowledgeBase | None:
        return await db.get(KnowledgeBase, kb_id)

    @staticmethod
    async def get_by_tenant_and_name(
        db: AsyncSession, tenant_id: str, name: str
    ) -> KnowledgeBase | None:
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.name == name,
                KnowledgeBase.status != "deleted",
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[list[KnowledgeBase], int]:
        base_filter = (
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.status != "deleted",
        )

        total_result = await db.execute(
            select(func.count()).select_from(KnowledgeBase).where(*base_filter)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(KnowledgeBase)
            .where(*base_filter)
            .order_by(KnowledgeBase.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> KnowledgeBase:
        item = KnowledgeBase(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: KnowledgeBase, data: dict
    ) -> KnowledgeBase:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def soft_delete(db: AsyncSession, item: KnowledgeBase) -> None:
        item.status = "deleted"
        await db.commit()
