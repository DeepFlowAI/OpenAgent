"""
PasswordResetCode repository
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_code import PasswordResetCode


class PasswordResetRepository:

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> PasswordResetCode:
        item = PasswordResetCode(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def find_valid_code(
        db: AsyncSession, tenant_id: str, username: str, code: str
    ) -> PasswordResetCode | None:
        result = await db.execute(
            select(PasswordResetCode).where(
                PasswordResetCode.tenant_id == tenant_id,
                PasswordResetCode.username == username,
                PasswordResetCode.code == code,
                PasswordResetCode.used == False,  # noqa: E712
                PasswordResetCode.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalars().first()

    @staticmethod
    async def mark_used(db: AsyncSession, item: PasswordResetCode) -> None:
        item.used = True
        await db.commit()

    @staticmethod
    async def count_recent(
        db: AsyncSession, tenant_id: str, username: str, since: datetime
    ) -> int:
        from sqlalchemy import func

        result = await db.execute(
            select(func.count()).select_from(PasswordResetCode).where(
                PasswordResetCode.tenant_id == tenant_id,
                PasswordResetCode.username == username,
                PasswordResetCode.created_at >= since,
            )
        )
        return result.scalar_one()
