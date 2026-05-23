"""
Tool executor base — abstract interface for all tool types.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolContext:
    """Runtime context passed to every tool executor."""
    db: AsyncSession
    conversation_id: int
    tenant_id: str
    agent_id: int
    conversation_source: str = "api"


class BaseToolExecutor(ABC):
    """Each tool_type implements this interface."""

    @abstractmethod
    async def execute(self, args: dict, config: dict, ctx: ToolContext) -> str:
        """Execute the tool and return a string response for the LLM.

        Args:
            args:   Parsed arguments from LLM's function call (already JSON-decoded).
            config: Tool instance config from AgentTool.config (knowledge_base_id, fixed_filters, etc.).
            ctx:    Runtime context (db session, conversation/tenant IDs).

        Returns:
            A string that will be placed into the `tool` message's `content`.
        """
        ...
