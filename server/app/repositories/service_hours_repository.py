"""
Service hours repository.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_hours import ServiceHours


class ServiceHoursRepository:

    @staticmethod
    async def get_by_id(
        db: AsyncSession, service_hours_id: int
    ) -> ServiceHours | None:
        return await db.get(ServiceHours, service_hours_id)

    @staticmethod
    async def get_by_tenant_and_name(
        db: AsyncSession,
        tenant_id: str,
        name: str,
        exclude_id: int | None = None,
    ) -> ServiceHours | None:
        stmt = select(ServiceHours).where(
            ServiceHours.tenant_id == tenant_id,
            ServiceHours.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(ServiceHours.id != exclude_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[list[ServiceHours], int]:
        total_result = await db.execute(
            select(func.count()).select_from(ServiceHours).where(
                ServiceHours.tenant_id == tenant_id
            )
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(ServiceHours)
            .where(ServiceHours.tenant_id == tenant_id)
            .order_by(ServiceHours.updated_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ServiceHours:
        item = ServiceHours(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: ServiceHours, data: dict
    ) -> ServiceHours:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: ServiceHours) -> None:
        await db.delete(item)
        await db.commit()
