"""
Help Center Tab repository — data access only, no business rules.
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.help_center_tab import HelpCenterTab


class HelpCenterTabRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, tab_id: int) -> HelpCenterTab | None:
        return await db.get(HelpCenterTab, tab_id)

    @staticmethod
    async def list_by_help_center(
        db: AsyncSession, help_center_id: int
    ) -> list[HelpCenterTab]:
        """List tabs ordered by sort_order ASC, id ASC for stable display."""
        result = await db.execute(
            select(HelpCenterTab)
            .where(HelpCenterTab.help_center_id == help_center_id)
            .order_by(HelpCenterTab.sort_order.asc(), HelpCenterTab.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_help_center_and_slug(
        db: AsyncSession,
        help_center_id: int,
        tab_slug: str,
        exclude_id: int | None = None,
    ) -> HelpCenterTab | None:
        stmt = select(HelpCenterTab).where(
            HelpCenterTab.help_center_id == help_center_id,
            HelpCenterTab.tab_slug == tab_slug,
        )
        if exclude_id is not None:
            stmt = stmt.where(HelpCenterTab.id != exclude_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def max_sort_order(
        db: AsyncSession, help_center_id: int
    ) -> int:
        """Returns the largest sort_order in this Help Center, or -1 when empty.
        Callers add 1 to get the slot for a new row appended at the end."""
        result = await db.execute(
            select(func.max(HelpCenterTab.sort_order)).where(
                HelpCenterTab.help_center_id == help_center_id
            )
        )
        v = result.scalar_one()
        return -1 if v is None else int(v)

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> HelpCenterTab:
        item = HelpCenterTab(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: HelpCenterTab, data: dict
    ) -> HelpCenterTab:
        for k, v in data.items():
            if hasattr(item, k):
                setattr(item, k, v)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: HelpCenterTab) -> None:
        await db.delete(item)
        await db.commit()

    @staticmethod
    async def reorder(
        db: AsyncSession, help_center_id: int, ordered_ids: list[int]
    ) -> list[HelpCenterTab]:
        """Rewrite sort_order for every tab in the Help Center based on the
        positions of `ordered_ids`. Caller must verify that ordered_ids is
        the exact set of tabs under the Help Center."""
        rows = await HelpCenterTabRepository.list_by_help_center(
            db, help_center_id
        )
        by_id = {r.id: r for r in rows}
        for idx, tab_id in enumerate(ordered_ids):
            row = by_id.get(tab_id)
            if row is None:
                continue  # validated by service before this call
            row.sort_order = idx
        await db.commit()
        return await HelpCenterTabRepository.list_by_help_center(
            db, help_center_id
        )
