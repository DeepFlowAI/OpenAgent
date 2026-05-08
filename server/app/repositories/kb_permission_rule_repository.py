"""
KbPermissionRule repository
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb_permission_rule import KbPermissionRule


class KbPermissionRuleRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, rule_id: int) -> KbPermissionRule | None:
        return await db.get(KbPermissionRule, rule_id)

    @staticmethod
    async def list_by_kb(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
    ) -> list[KbPermissionRule]:
        result = await db.execute(
            select(KbPermissionRule)
            .where(
                KbPermissionRule.tenant_id == tenant_id,
                KbPermissionRule.knowledge_base_id == knowledge_base_id,
            )
            .order_by(KbPermissionRule.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_enabled_by_kb(
        db: AsyncSession,
        knowledge_base_id: int,
    ) -> list[KbPermissionRule]:
        """Get all enabled rules for a KB (used by permission engine at runtime)."""
        result = await db.execute(
            select(KbPermissionRule)
            .where(
                KbPermissionRule.knowledge_base_id == knowledge_base_id,
                KbPermissionRule.enabled.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> KbPermissionRule:
        item = KbPermissionRule(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: KbPermissionRule, data: dict
    ) -> KbPermissionRule:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: KbPermissionRule) -> None:
        await db.delete(item)
        await db.commit()
