"""
API Key repository
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey


class ApiKeyRepository:

    @staticmethod
    async def get_by_tenant_id(db: AsyncSession, tenant_id: str) -> ApiKey | None:
        """Get the first active key for a tenant (legacy single-key compat)."""
        result = await db.execute(
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id, ApiKey.status == "active")
            .order_by(ApiKey.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_key_value(db: AsyncSession, key_value: str) -> ApiKey | None:
        result = await db.execute(
            select(ApiKey).where(ApiKey.key_value == key_value)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, key_id: int) -> ApiKey | None:
        return await db.get(ApiKey, key_id)

    @staticmethod
    async def list_by_tenant(
        db: AsyncSession, tenant_id: str, page: int = 1, per_page: int = 20
    ) -> tuple[list[ApiKey], int]:
        total_result = await db.execute(
            select(func.count()).select_from(ApiKey).where(ApiKey.tenant_id == tenant_id)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id)
            .order_by(ApiKey.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ApiKey:
        item = ApiKey(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: ApiKey, data: dict) -> ApiKey:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: ApiKey) -> None:
        await db.delete(item)
        await db.commit()
