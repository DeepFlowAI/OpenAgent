"""
Agent service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.agent_repository import AgentRepository
from app.repositories.agent_tool_repository import AgentToolRepository
from app.schemas.agent import AgentCreate, AgentUpdate, AgentStatusUpdate, EngineConfigUpdate, EngineConfig


class AgentService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        status: str = "active",
        page: int = 1,
        per_page: int = 10,
    ) -> dict:
        items, total = await AgentRepository.get_paginated(
            db, tenant_id, status, page, per_page
        )
        pages = (total + per_page - 1) // per_page
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, agent_id: int) -> dict:
        item = await AgentRepository.get_by_id(db, agent_id)
        if not item:
            raise NotFoundError("Agent not found")
        return item

    @staticmethod
    async def create(db: AsyncSession, data: AgentCreate) -> dict:
        name_stripped = data.name.strip()
        if not name_stripped:
            raise ValidationError("Agent name cannot be blank")

        existing = await AgentRepository.get_by_tenant_and_name(
            db, data.tenant_id, name_stripped
        )
        if existing:
            raise ValidationError(
                f"Agent with name '{name_stripped}' already exists"
            )

        create_data = data.model_dump()
        create_data["name"] = name_stripped
        agent = await AgentRepository.create(db, create_data)

        await AgentToolRepository.create_system_tools(
            db, agent.id, agent.tenant_id
        )

        return agent

    @staticmethod
    async def update(
        db: AsyncSession, agent_id: int, data: AgentUpdate
    ) -> dict:
        item = await AgentRepository.get_by_id(db, agent_id)
        if not item:
            raise NotFoundError("Agent not found")

        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data:
            name_stripped = update_data["name"].strip()
            if not name_stripped:
                raise ValidationError("Agent name cannot be blank")
            update_data["name"] = name_stripped

            if name_stripped != item.name:
                existing = await AgentRepository.get_by_tenant_and_name(
                    db, item.tenant_id, name_stripped
                )
                if existing:
                    raise ValidationError(
                        f"Agent with name '{name_stripped}' already exists"
                    )

        return await AgentRepository.update(db, item, update_data)

    @staticmethod
    async def update_status(
        db: AsyncSession, agent_id: int, data: AgentStatusUpdate
    ) -> dict:
        item = await AgentRepository.get_by_id(db, agent_id)
        if not item:
            raise NotFoundError("Agent not found")

        return await AgentRepository.update(db, item, {"status": data.status})

    @staticmethod
    async def update_engine_config(
        db: AsyncSession, agent_id: int, data: EngineConfigUpdate
    ):
        item = await AgentRepository.get_by_id(db, agent_id)
        if not item:
            raise NotFoundError("Agent not found")

        current_config = item.engine_config or {}
        defaults = EngineConfig().model_dump()

        merged = {**defaults, **current_config}

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value

        EngineConfig(**merged)

        return await AgentRepository.update(db, item, {"engine_config": merged})
