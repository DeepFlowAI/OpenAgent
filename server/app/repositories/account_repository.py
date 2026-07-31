"""Tenant account data access."""

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.knowledge_base import KnowledgeBase
from app.models.tenant_account import (
    TenantAccount,
    TenantAccountAgent,
    TenantAccountKnowledgeBase,
)


class AccountRepository:
    """Repository for tenant accounts and their explicit resource grants."""

    @staticmethod
    async def get_by_id(
        db: AsyncSession, tenant_id: str, account_id: int
    ) -> TenantAccount | None:
        result = await db.execute(
            select(TenantAccount).where(
                TenantAccount.id == account_id,
                TenantAccount.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_identifier(
        db: AsyncSession, tenant_id: str, identifier: str
    ) -> TenantAccount | None:
        normalized = identifier.strip().lower()
        column = (
            TenantAccount.email_normalized
            if "@" in normalized
            else TenantAccount.username_normalized
        )
        result = await db.execute(
            select(TenantAccount).where(
                TenantAccount.tenant_id == tenant_id,
                column == normalized,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_accounts(db: AsyncSession, tenant_id: str) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(TenantAccount)
            .where(TenantAccount.tenant_id == tenant_id)
        )
        return result.scalar_one()

    @staticmethod
    async def get_primary_admin(
        db: AsyncSession, tenant_id: str, username: str | None = None
    ) -> TenantAccount | None:
        conditions = [
            TenantAccount.tenant_id == tenant_id,
            TenantAccount.role == "admin",
        ]
        if username:
            conditions.append(TenantAccount.username_normalized == username.lower())
        result = await db.execute(
            select(TenantAccount)
            .where(*conditions)
            .order_by(TenantAccount.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        *,
        q: str | None,
        role: str | None,
        page: int,
        per_page: int,
    ) -> tuple[list[TenantAccount], int]:
        conditions = [TenantAccount.tenant_id == tenant_id]
        if q:
            pattern = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    TenantAccount.username_normalized.ilike(pattern),
                    TenantAccount.email_normalized.ilike(pattern),
                )
            )
        if role:
            conditions.append(TenantAccount.role == role)

        total = (
            await db.execute(
                select(func.count()).select_from(TenantAccount).where(*conditions)
            )
        ).scalar_one()
        result = await db.execute(
            select(TenantAccount)
            .where(*conditions)
            .order_by(TenantAccount.updated_at.desc(), TenantAccount.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> TenantAccount:
        item = TenantAccount(**data)
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: TenantAccount, data: dict
    ) -> TenantAccount:
        for key, value in data.items():
            setattr(item, key, value)
        await db.flush()
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: TenantAccount) -> None:
        await db.delete(item)
        await db.flush()

    @staticmethod
    async def count_admins(db: AsyncSession, tenant_id: str) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(TenantAccount)
            .where(
                TenantAccount.tenant_id == tenant_id,
                TenantAccount.role == "admin",
            )
        )
        return result.scalar_one()

    @staticmethod
    async def lock_admins(db: AsyncSession, tenant_id: str) -> list[int]:
        result = await db.execute(
            select(TenantAccount.id)
            .where(
                TenantAccount.tenant_id == tenant_id,
                TenantAccount.role == "admin",
            )
            .with_for_update()
        )
        return list(result.scalars().all())

    @staticmethod
    async def replace_access(
        db: AsyncSession,
        account_id: int,
        *,
        agent_ids: list[int],
        knowledge_base_ids: list[int],
    ) -> None:
        await db.execute(
            delete(TenantAccountAgent).where(
                TenantAccountAgent.account_id == account_id
            )
        )
        await db.execute(
            delete(TenantAccountKnowledgeBase).where(
                TenantAccountKnowledgeBase.account_id == account_id
            )
        )
        db.add_all(
            TenantAccountAgent(account_id=account_id, agent_id=agent_id)
            for agent_id in agent_ids
        )
        db.add_all(
            TenantAccountKnowledgeBase(
                account_id=account_id, knowledge_base_id=knowledge_base_id
            )
            for knowledge_base_id in knowledge_base_ids
        )
        await db.flush()

    @staticmethod
    async def get_agent_ids(db: AsyncSession, account_id: int) -> list[int]:
        result = await db.execute(
            select(TenantAccountAgent.agent_id)
            .where(TenantAccountAgent.account_id == account_id)
            .order_by(TenantAccountAgent.agent_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_knowledge_base_ids(
        db: AsyncSession, account_id: int
    ) -> list[int]:
        result = await db.execute(
            select(TenantAccountKnowledgeBase.knowledge_base_id)
            .where(TenantAccountKnowledgeBase.account_id == account_id)
            .order_by(TenantAccountKnowledgeBase.knowledge_base_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def has_agent_access(
        db: AsyncSession, account_id: int, agent_id: int
    ) -> bool:
        result = await db.execute(
            select(TenantAccountAgent.account_id).where(
                TenantAccountAgent.account_id == account_id,
                TenantAccountAgent.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def has_knowledge_base_access(
        db: AsyncSession, account_id: int, knowledge_base_id: int
    ) -> bool:
        result = await db.execute(
            select(TenantAccountKnowledgeBase.account_id).where(
                TenantAccountKnowledgeBase.account_id == account_id,
                TenantAccountKnowledgeBase.knowledge_base_id == knowledge_base_id,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_access_names(
        db: AsyncSession, account_ids: list[int]
    ) -> tuple[dict[int, list[tuple[int, str]]], dict[int, list[tuple[int, str]]]]:
        if not account_ids:
            return {}, {}
        agent_rows = (
            await db.execute(
                select(
                    TenantAccountAgent.account_id,
                    Agent.id,
                    Agent.name,
                )
                .join(Agent, Agent.id == TenantAccountAgent.agent_id)
                .where(TenantAccountAgent.account_id.in_(account_ids))
                .order_by(Agent.name.asc())
            )
        ).all()
        kb_rows = (
            await db.execute(
                select(
                    TenantAccountKnowledgeBase.account_id,
                    KnowledgeBase.id,
                    KnowledgeBase.name,
                )
                .join(
                    KnowledgeBase,
                    KnowledgeBase.id
                    == TenantAccountKnowledgeBase.knowledge_base_id,
                )
                .where(
                    TenantAccountKnowledgeBase.account_id.in_(account_ids),
                    KnowledgeBase.status != "deleted",
                )
                .order_by(KnowledgeBase.name.asc())
            )
        ).all()
        agents: dict[int, list[tuple[int, str]]] = {}
        knowledge_bases: dict[int, list[tuple[int, str]]] = {}
        for account_id, resource_id, name in agent_rows:
            agents.setdefault(account_id, []).append((resource_id, name))
        for account_id, resource_id, name in kb_rows:
            knowledge_bases.setdefault(account_id, []).append((resource_id, name))
        return agents, knowledge_bases

    @staticmethod
    async def validate_agent_ids(
        db: AsyncSession, tenant_id: str, agent_ids: list[int]
    ) -> bool:
        if not agent_ids:
            return True
        count = (
            await db.execute(
                select(func.count())
                .select_from(Agent)
                .where(Agent.tenant_id == tenant_id, Agent.id.in_(agent_ids))
            )
        ).scalar_one()
        return count == len(set(agent_ids))

    @staticmethod
    async def validate_knowledge_base_ids(
        db: AsyncSession, tenant_id: str, knowledge_base_ids: list[int]
    ) -> bool:
        if not knowledge_base_ids:
            return True
        count = (
            await db.execute(
                select(func.count())
                .select_from(KnowledgeBase)
                .where(
                    KnowledgeBase.tenant_id == tenant_id,
                    KnowledgeBase.status != "deleted",
                    KnowledgeBase.id.in_(knowledge_base_ids),
                )
            )
        ).scalar_one()
        return count == len(set(knowledge_base_ids))

    @staticmethod
    async def get_resource_options(
        db: AsyncSession, tenant_id: str
    ) -> tuple[list[Agent], list[KnowledgeBase]]:
        agents = (
            await db.execute(
                select(Agent)
                .where(Agent.tenant_id == tenant_id)
                .order_by(Agent.name.asc())
            )
        ).scalars().all()
        knowledge_bases = (
            await db.execute(
                select(KnowledgeBase)
                .where(
                    KnowledgeBase.tenant_id == tenant_id,
                    KnowledgeBase.status != "deleted",
                )
                .order_by(KnowledgeBase.name.asc())
            )
        ).scalars().all()
        return list(agents), list(knowledge_bases)
