"""
Super admin repository — data access layer
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.super_admin import SuperAdmin


class SuperAdminRepository:

    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> SuperAdmin | None:
        result = await db.execute(
            select(SuperAdmin).where(SuperAdmin.username == username)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, admin_id: int) -> SuperAdmin | None:
        return await db.get(SuperAdmin, admin_id)
