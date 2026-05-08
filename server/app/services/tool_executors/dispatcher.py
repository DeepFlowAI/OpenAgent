"""
Tool execution dispatcher — routes tool calls to the appropriate executor by tool_type.
"""
import logging

from app.services.tool_executors.base import BaseToolExecutor, ToolContext
from app.services.tool_executors.search_executor import SearchToolExecutor
from app.services.tool_executors.doc_query_executor import DocQueryToolExecutor
from app.services.tool_executors.notebook_executor import NotebookToolExecutor
from app.services.tool_executors.fetch_executor import ToolResponseFetchExecutor

logger = logging.getLogger(__name__)

_EXECUTORS: dict[str, BaseToolExecutor] = {
    "search": SearchToolExecutor(),
    "doc_query": DocQueryToolExecutor(),
    "notebook": NotebookToolExecutor(),
    "tool_response_fetch": ToolResponseFetchExecutor(),
}


async def execute_tool(
    tool_name: str,
    tool_type: str,
    args: dict,
    config: dict,
    ctx: ToolContext,
) -> str:
    """Dispatch a tool call to the matching executor.

    Args:
        tool_name: The tool instance name (e.g. "knowledge_search").
        tool_type: The tool_type from AgentTool (e.g. "search", "doc_query").
        args:      Parsed arguments from LLM function call.
        config:    AgentTool.config dict.
        ctx:       Runtime context (db, conversation_id, etc.).

    Returns:
        String response for the tool message.
    """
    executor = _EXECUTORS.get(tool_type)
    if executor is None:
        logger.warning("No executor for tool_type=%s (tool_name=%s)", tool_type, tool_name)
        return f"Error: tool type '{tool_type}' is not supported."

    logger.info("Executing tool — name=%s, type=%s", tool_name, tool_type)

    try:
        return await executor.execute(args, config, ctx)
    except Exception:
        logger.exception("Tool execution failed — name=%s, type=%s", tool_name, tool_type)
        return f"Error: tool '{tool_name}' execution failed."
