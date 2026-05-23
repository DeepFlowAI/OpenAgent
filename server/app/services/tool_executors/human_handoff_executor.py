"""
Human handoff tool executor.
"""
from html import escape

from app.repositories.conversation_repository import ConversationRepository
from app.schemas.agent_tool import normalize_human_handoff_arguments
from app.services.tool_executors.base import BaseToolExecutor, ToolContext


def _error(code: str, message: str) -> str:
    return (
        f'<human_handoff_response status="error" code="{escape(code)}">'
        f"{escape(message)}"
        "</human_handoff_response>"
    )


class HumanHandoffToolExecutor(BaseToolExecutor):
    """Validate a human handoff request and return a model-readable result."""

    async def execute(self, args: dict, config: dict, ctx: ToolContext) -> str:
        conversation = await ConversationRepository.get_by_id(
            ctx.db, ctx.conversation_id
        )
        if (
            conversation is None
            or conversation.tenant_id != ctx.tenant_id
            or conversation.agent_id != ctx.agent_id
        ):
            return _error("conversation_not_found", "Conversation not found.")

        if conversation.source != "api" or ctx.conversation_source != "api":
            return _error(
                "unsupported_source",
                "Human handoff is only available for API conversations.",
            )

        try:
            handoff = normalize_human_handoff_arguments(args, config)
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))

        return (
            '<human_handoff_response status="recorded">'
            f"<brief>{escape(handoff['brief'])}</brief>"
            "<instruction>"
            "The request has been recorded. Tell the user that follow-up has been logged, "
            "and do not claim that a human agent has joined this chat in real time."
            "</instruction>"
            "</human_handoff_response>"
        )
