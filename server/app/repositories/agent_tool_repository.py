"""
AgentTool repository
"""
from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_tool import AgentTool
from app.schemas.agent_tool import (
    DEFAULT_HUMAN_HANDOFF_CONFIG,
    DOC_GREP_PARAMETERS_SCHEMA,
    HUMAN_HANDOFF_PARAMETERS_SCHEMA,
    HUMAN_HANDOFF_TOOL_NAME,
    HUMAN_HANDOFF_TOOL_TYPE,
    NOTEBOOK_PARAMETERS_SCHEMA,
    build_human_handoff_parameters_schema,
)


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
            "parameters_schema": NOTEBOOK_PARAMETERS_SCHEMA,
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
        {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "tool_type": HUMAN_HANDOFF_TOOL_TYPE,
            "name": HUMAN_HANDOFF_TOOL_NAME,
            "description": (
                "Request human support when the user explicitly asks for a person, "
                "the issue requires manual handling, or automated assistance cannot safely continue. "
                "The conversation will pause and wait for the caller to submit the tool result."
            ),
            "is_system": True,
            "is_enabled": False,
            "parameters_schema": HUMAN_HANDOFF_PARAMETERS_SCHEMA,
            "config": deepcopy(DEFAULT_HUMAN_HANDOFF_CONFIG),
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
        system_data = _system_tool_data(agent_id, tenant_id)
        canonical_by_name = {data["name"]: data for data in system_data}
        existing = await AgentToolRepository.get_by_agent_id(db, agent_id)
        changed = False
        for tool in existing:
            canonical = canonical_by_name.get(tool.name)
            if not tool.is_system or not canonical:
                continue
            if canonical["tool_type"] == HUMAN_HANDOFF_TOOL_TYPE:
                if tool.tool_type != HUMAN_HANDOFF_TOOL_TYPE:
                    tool.tool_type = HUMAN_HANDOFF_TOOL_TYPE
                    changed = True
                if not tool.parameters_schema:
                    tool.parameters_schema = build_human_handoff_parameters_schema(
                        tool.config or {}
                    )
                    changed = True
                continue
            for key in ("description", "parameters_schema", "tool_type"):
                value = canonical[key]
                if getattr(tool, key) != value:
                    setattr(tool, key, value)
                    changed = True

        existing_system_names = {tool.name for tool in existing if tool.is_system}
        missing = [
            data
            for data in system_data
            if data["name"] not in existing_system_names
        ]
        if not missing and not changed:
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
