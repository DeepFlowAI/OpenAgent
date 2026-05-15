"""
AgentTool repository
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_tool import AgentTool
from app.schemas.agent_tool import DOC_GREP_PARAMETERS_SCHEMA


def _system_tool_data(agent_id: int, tenant_id: str) -> list[dict]:
    """Build default system tool rows for an agent."""
    return [
        {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "tool_type": "notebook",
            "name": "notebook",
            "description": "Manage a notebook to collect and organize important information during the conversation.",
            "is_system": True,
            "is_enabled": True,
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "brief": {
                        "type": "string",
                        "description": "One-line summary for session log display",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["add", "remove"],
                        "description": "Operation type: add or remove items",
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "slice_id": {"type": "string"},
                                "doc_id": {"type": "string"},
                                "text": {"type": "string"},
                                "id": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["brief", "action", "items"],
            },
            "config": {},
        },
        {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "tool_type": "tool_response_fetch",
            "name": "tool_response_fetch",
            "description": "Fetch the full body of a previous tool response by tool_response_id.",
            "is_system": True,
            "is_enabled": True,
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "brief": {
                        "type": "string",
                        "description": "One-line summary for session log display",
                    },
                    "tool_response_id": {
                        "type": "string",
                        "description": "Tool response id from the ID reference line, e.g. sr_7f3a",
                    },
                },
                "required": ["brief", "tool_response_id"],
            },
            "config": {},
        },
        {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "tool_type": "doc_grep",
            "name": "doc_grep",
            "description": (
                "Search within a single document using Python regex. Use after locating a document via "
                "search or doc_query to find specific content by pattern. Pass the doc_id from prior "
                "tool results and a regex pattern."
            ),
            "is_system": True,
            "is_enabled": True,
            "parameters_schema": DOC_GREP_PARAMETERS_SCHEMA,
            "config": {},
        },
    ]


class AgentToolRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, tool_id: int) -> AgentTool | None:
        return await db.get(AgentTool, tool_id)

    @staticmethod
    async def get_by_agent_id(db: AsyncSession, agent_id: int) -> list[AgentTool]:
        result = await db.execute(
            select(AgentTool)
            .where(AgentTool.agent_id == agent_id)
            .order_by(AgentTool.is_system.desc(), AgentTool.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_agent_and_name(
        db: AsyncSession, agent_id: int, name: str
    ) -> AgentTool | None:
        result = await db.execute(
            select(AgentTool).where(
                AgentTool.agent_id == agent_id,
                AgentTool.name == name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_enabled_by_agent(db: AsyncSession, agent_id: int) -> list[AgentTool]:
        result = await db.execute(
            select(AgentTool).where(
                AgentTool.agent_id == agent_id,
                AgentTool.is_enabled.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> AgentTool:
        item = AgentTool(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: AgentTool, data: dict) -> AgentTool:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete(db: AsyncSession, item: AgentTool) -> None:
        await db.delete(item)
        await db.commit()

    @staticmethod
    async def create_system_tools(
        db: AsyncSession, agent_id: int, tenant_id: str
    ) -> list[AgentTool]:
        """Create default system tools for a new agent."""
        tools = []
        for data in _system_tool_data(agent_id, tenant_id):
            tool = AgentTool(**data)
            db.add(tool)
            tools.append(tool)
        await db.commit()
        for tool in tools:
            await db.refresh(tool)
        return tools

    @staticmethod
    async def ensure_system_tools(
        db: AsyncSession, agent_id: int, tenant_id: str
    ) -> list[AgentTool]:
        """Create any missing system tools without duplicating existing ones."""
        existing = await AgentToolRepository.get_by_agent_id(db, agent_id)
        existing_system_names = {tool.name for tool in existing if tool.is_system}
        missing = [
            data
            for data in _system_tool_data(agent_id, tenant_id)
            if data["name"] not in existing_system_names
        ]
        if not missing:
            return []

        tools = []
        for data in missing:
            tool = AgentTool(**data)
            db.add(tool)
            tools.append(tool)
        await db.commit()
        for tool in tools:
            await db.refresh(tool)
        return tools
