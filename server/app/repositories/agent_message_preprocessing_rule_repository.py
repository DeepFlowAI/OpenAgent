"""
Agent message preprocessing rule repository
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_message_preprocessing_rule import AgentMessagePreprocessingRule


class AgentMessagePreprocessingRuleRepository:

    @staticmethod
    async def list_by_agent(
        db: AsyncSession, tenant_id: str, agent_id: int
    ) -> list[AgentMessagePreprocessingRule]:
        result = await db.execute(
            select(AgentMessagePreprocessingRule)
            .where(
                AgentMessagePreprocessingRule.tenant_id == tenant_id,
                AgentMessagePreprocessingRule.agent_id == agent_id,
            )
            .order_by(AgentMessagePreprocessingRule.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(
        db: AsyncSession, rule_id: int
    ) -> AgentMessagePreprocessingRule | None:
        return await db.get(AgentMessagePreprocessingRule, rule_id)

    @staticmethod
    async def create(
        db: AsyncSession, data: dict
    ) -> AgentMessagePreprocessingRule:
        item = AgentMessagePreprocessingRule(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: AgentMessagePreprocessingRule, data: dict
    ) -> AgentMessagePreprocessingRule:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(
        db: AsyncSession, item: AgentMessagePreprocessingRule
    ) -> None:
        await db.delete(item)
        await db.commit()
