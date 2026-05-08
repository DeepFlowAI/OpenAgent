"""
Tool response fetch executor — retrieves a full tool response by tool_response_id
from conversation_step records.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_step import ConversationStep
from app.services.tool_executors.base import BaseToolExecutor, ToolContext

logger = logging.getLogger(__name__)


class ToolResponseFetchExecutor(BaseToolExecutor):

    async def execute(self, args: dict, config: dict, ctx: ToolContext) -> str:
        tool_response_id = args.get("tool_response_id", "").strip()
        if not tool_response_id:
            return "Error: tool_response_id is required."

        logger.info(
            "Fetch tool response — id=%s, conversation=%d",
            tool_response_id, ctx.conversation_id,
        )

        content = await _fetch_response_by_id(
            ctx.db, ctx.conversation_id, tool_response_id,
        )

        if content is None:
            logger.warning("Tool response not found: %s", tool_response_id)
            return f"Error: tool response '{tool_response_id}' not found in this conversation."

        logger.info("Fetched tool response %s (%d chars)", tool_response_id, len(content))
        return content


async def _fetch_response_by_id(
    db: AsyncSession,
    conversation_id: int,
    tool_response_id: str,
) -> str | None:
    """Look up the tool_response column from conversation_steps
    where step_type='tool' and metadata contains the matching tool_response_id.
    """
    result = await db.execute(
        select(ConversationStep.tool_response)
        .where(
            ConversationStep.conversation_id == conversation_id,
            ConversationStep.step_type == "tool",
            ConversationStep.metadata_["tool_response_id"].astext == tool_response_id,
        )
        .order_by(ConversationStep.step_order.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row
