"""
Human handoff event persistence helpers.
"""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.conversation_step_repository import ConversationStepRepository
from app.schemas.agent_tool import (
    HUMAN_HANDOFF_EVENT_KIND,
    HUMAN_HANDOFF_EVENT_STEP_TYPE,
    HUMAN_HANDOFF_SCHEMA_VERSION,
    normalize_human_handoff_arguments,
)


async def create_human_handoff_event_step(
    db: AsyncSession,
    conv: Any,
    agent_id: int,
    round_number: int,
    tool_step: Any,
    tool_args: dict,
    tool_config: dict | None,
):
    """Persist a customer-service handoff event for a completed handoff tool call."""
    handoff = normalize_human_handoff_arguments(tool_args, tool_config or {})
    requested_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {
        "event_kind": HUMAN_HANDOFF_EVENT_KIND,
        "schema_version": HUMAN_HANDOFF_SCHEMA_VERSION,
        "related_tool_call_step_id": tool_step.id,
        "conversation": {
            "id": conv.id,
            "external_id": getattr(conv, "external_id", None),
        },
        "tenant_id": conv.tenant_id,
        "agent_id": agent_id,
        "requested_at": requested_at,
        "handoff": handoff,
    }
    max_order = await ConversationStepRepository.get_max_step_order(db, conv.id)
    return await ConversationStepRepository.create(
        db,
        {
            "conversation_id": conv.id,
            "tenant_id": conv.tenant_id,
            "round_number": round_number,
            "step_order": max_order + 1,
            "step_type": HUMAN_HANDOFF_EVENT_STEP_TYPE,
            "content": handoff["brief"],
            "brief": handoff["brief"],
            "parent_step_id": tool_step.id,
            "metadata": payload,
        },
    )
