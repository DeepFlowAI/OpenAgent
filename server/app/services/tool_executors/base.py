"""
Tool executor base — abstract interface for all tool types.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


def str_arg(args: dict, key: str, default: str = "") -> str:
    """Return ``args[key]`` as a stripped string.

    LLM-generated tool arguments are untrusted: the model sometimes emits a
    field as a list/int/null instead of the expected string. Those degrade to
    ``default`` here instead of raising ``AttributeError`` (e.g. ``'list'
    object has no attribute 'strip'``) deep inside an executor, which the
    dispatcher would only surface as a generic ERROR-logged tool failure.
    """
    value = args.get(key, default)
    return value.strip() if isinstance(value, str) else default


def dict_arg(args: dict, key: str) -> dict:
    """Return ``args[key]`` if it is a dict, else ``{}``.

    Same rationale as :func:`str_arg`: the model occasionally passes an
    object-typed arg (e.g. ``filter``) as a bare string or list, which would
    otherwise crash with ``'str' object has no attribute 'get'``.
    """
    value = args.get(key)
    return value if isinstance(value, dict) else {}


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
