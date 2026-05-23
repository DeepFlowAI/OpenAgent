"""
Agent message preprocessing rule service
"""
import regex
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.agent_message_preprocessing_rule_repository import (
    AgentMessagePreprocessingRuleRepository,
)
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent_message_preprocessing_rule import (
    AgentMessagePreprocessingRuleCreate,
    AgentMessagePreprocessingRuleUpdate,
)


class AgentMessagePreprocessingRuleService:

    @staticmethod
    async def _ensure_agent(db: AsyncSession, tenant_id: str, agent_id: int):
        agent = await AgentRepository.get_by_id(db, agent_id)
        if not agent or agent.tenant_id != tenant_id:
            raise NotFoundError("Agent not found")
        return agent

    @staticmethod
    def _validate_condition(condition: str) -> None:
        try:
            regex.compile(condition)
        except regex.error as exc:
            raise ValidationError("Invalid regular expression") from exc

    @staticmethod
    async def list_rules(
        db: AsyncSession, tenant_id: str, agent_id: int
    ) -> dict:
        await AgentMessagePreprocessingRuleService._ensure_agent(
            db, tenant_id, agent_id
        )
        items = await AgentMessagePreprocessingRuleRepository.list_by_agent(
            db, tenant_id, agent_id
        )
        return {"items": items, "total": len(items)}

    @staticmethod
    async def get_by_id(
        db: AsyncSession, tenant_id: str, agent_id: int, rule_id: int
    ):
        await AgentMessagePreprocessingRuleService._ensure_agent(
            db, tenant_id, agent_id
        )
        item = await AgentMessagePreprocessingRuleRepository.get_by_id(db, rule_id)
        if not item or item.tenant_id != tenant_id or item.agent_id != agent_id:
            raise NotFoundError("Preprocessing rule not found")
        return item

    @staticmethod
    async def create(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        data: AgentMessagePreprocessingRuleCreate,
    ):
        await AgentMessagePreprocessingRuleService._ensure_agent(
            db, tenant_id, agent_id
        )
        AgentMessagePreprocessingRuleService._validate_condition(data.condition)
        create_data = data.model_dump()
        create_data["tenant_id"] = tenant_id
        create_data["agent_id"] = agent_id
        return await AgentMessagePreprocessingRuleRepository.create(db, create_data)

    @staticmethod
    async def update(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        rule_id: int,
        data: AgentMessagePreprocessingRuleUpdate,
    ):
        item = await AgentMessagePreprocessingRuleService.get_by_id(
            db, tenant_id, agent_id, rule_id
        )
        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        if "condition" in update_data:
            AgentMessagePreprocessingRuleService._validate_condition(
                update_data["condition"]
            )
        return await AgentMessagePreprocessingRuleRepository.update(
            db, item, update_data
        )

    @staticmethod
    async def delete(
        db: AsyncSession, tenant_id: str, agent_id: int, rule_id: int
    ) -> None:
        item = await AgentMessagePreprocessingRuleService.get_by_id(
            db, tenant_id, agent_id, rule_id
        )
        await AgentMessagePreprocessingRuleRepository.delete(db, item)
