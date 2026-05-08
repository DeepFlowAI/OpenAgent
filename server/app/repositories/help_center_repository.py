"""
Help Center repository — data access only, no business rules.
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.help_center import HelpCenter


class HelpCenterRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, help_center_id: int) -> HelpCenter | None:
        return await db.get(HelpCenter, help_center_id)

    @staticmethod
    async def get_by_public_slug(
        db: AsyncSession,
        public_slug: str,
        exclude_id: int | None = None,
    ) -> HelpCenter | None:
        """Look up an existing slug owner GLOBALLY (across all tenants).
        `exclude_id` lets the caller skip the row being updated when
        checking uniqueness during an update."""
        stmt = select(HelpCenter).where(
            HelpCenter.public_slug == public_slug,
        )
        if exclude_id is not None:
            stmt = stmt.where(HelpCenter.id != exclude_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[list[HelpCenter], int]:
        base_filter = (HelpCenter.tenant_id == tenant_id,)

        total_result = await db.execute(
            select(func.count()).select_from(HelpCenter).where(*base_filter)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(HelpCenter)
            .where(*base_filter)
            .order_by(HelpCenter.updated_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> HelpCenter:
        item = HelpCenter(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: HelpCenter, data: dict
    ) -> HelpCenter:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: HelpCenter) -> None:
        await db.delete(item)
        await db.commit()
