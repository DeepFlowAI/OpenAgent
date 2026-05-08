"""
Tenant repository — data access layer
"""
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


class TenantRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, tenant_id: int) -> Tenant | None:
        return await db.get(Tenant, tenant_id)

    @staticmethod
    async def get_by_name(db: AsyncSession, name: str) -> Tenant | None:
        result = await db.execute(select(Tenant).where(Tenant.name == name))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_tenant_id(db: AsyncSession, tenant_id: str) -> Tenant | None:
        result = await db.execute(
            select(Tenant).where(Tenant.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
        result = await db.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_identifier(
        db: AsyncSession, identifier: str, slug_identifier: str | None = None
    ) -> list[Tenant]:
        slug_value = slug_identifier if slug_identifier is not None else identifier
        result = await db.execute(
            select(Tenant).where(
                or_(Tenant.tenant_id == identifier, Tenant.slug == slug_value)
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_paginated(
        db: AsyncSession, page: int = 1, per_page: int = 10
    ) -> tuple[list[Tenant], int]:
        total_result = await db.execute(select(func.count()).select_from(Tenant))
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(Tenant)
            .order_by(Tenant.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Tenant:
        item = Tenant(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: Tenant, data: dict) -> Tenant:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item
