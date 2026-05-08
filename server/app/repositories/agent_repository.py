"""
Agent repository
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent


class AgentRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, agent_id: int) -> Agent | None:
        return await db.get(Agent, agent_id)

    @staticmethod
    async def get_by_tenant_and_name(
        db: AsyncSession, tenant_id: str, name: str
    ) -> Agent | None:
        result = await db.execute(
            select(Agent).where(
                Agent.tenant_id == tenant_id,
                Agent.name == name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        status: str = "active",
        page: int = 1,
        per_page: int = 10,
    ) -> tuple[list[Agent], int]:
        base_filter = (
            Agent.tenant_id == tenant_id,
            Agent.status == status,
        )

        total_result = await db.execute(
            select(func.count()).select_from(Agent).where(*base_filter)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            select(Agent)
            .where(*base_filter)
            .order_by(Agent.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> Agent:
        item = Agent(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: Agent, data: dict) -> Agent:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item
