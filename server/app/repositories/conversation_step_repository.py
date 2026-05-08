"""
ConversationStep repository — data access for conversation_steps table
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_step import ConversationStep


# Columns excluded from timeline queries (large JSONB / TEXT)
_TIMELINE_EXCLUDE_COLUMNS = {"request_messages", "request_tools", "request_params", "tool_arguments", "tool_response"}

# For history building: keep tool_response (needed for tool messages) but exclude other large fields
_HISTORY_EXCLUDE_COLUMNS = {"request_messages", "request_tools", "request_params", "tool_arguments"}


class ConversationStepRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, step_id: int) -> ConversationStep | None:
        return await db.get(ConversationStep, step_id)

    @staticmethod
    async def get_timeline(
        db: AsyncSession,
        conversation_id: int,
    ) -> list[ConversationStep]:
        """Get all steps for a conversation ordered by step_order, excluding large fields."""
        columns = [
            c for c in ConversationStep.__table__.columns
            if c.key not in _TIMELINE_EXCLUDE_COLUMNS
        ]
        result = await db.execute(
            select(*columns)
            .where(ConversationStep.__table__.c.conversation_id == conversation_id)
            .order_by(ConversationStep.__table__.c.step_order.asc())
        )
        return list(result.mappings().all())

    @staticmethod
    async def get_history_steps(
        db: AsyncSession,
        conversation_id: int,
    ) -> list:
        """Get steps for history building, includes tool_response for tool messages."""
        columns = [
            c for c in ConversationStep.__table__.columns
            if c.key not in _HISTORY_EXCLUDE_COLUMNS
        ]
        result = await db.execute(
            select(*columns)
            .where(ConversationStep.__table__.c.conversation_id == conversation_id)
            .order_by(ConversationStep.__table__.c.step_order.asc())
        )
        return list(result.mappings().all())

    @staticmethod
    async def get_children(
        db: AsyncSession,
        parent_step_id: int,
    ) -> list[ConversationStep]:
        """Get child tool_call steps of a given parent step."""
        result = await db.execute(
            select(ConversationStep)
            .where(
                ConversationStep.parent_step_id == parent_step_id,
                ConversationStep.step_type == "tool_call",
            )
            .order_by(ConversationStep.step_order.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_round_tool_calls(
        db: AsyncSession,
        conversation_id: int,
        round_number: int,
    ) -> list[ConversationStep]:
        """Get all tool_call steps in the same round of a conversation."""
        result = await db.execute(
            select(ConversationStep)
            .where(
                ConversationStep.conversation_id == conversation_id,
                ConversationStep.step_type == "tool_call",
                ConversationStep.round_number == round_number,
            )
            .order_by(ConversationStep.step_order.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_steps_by_round(
        db: AsyncSession,
        conversation_id: int,
        round_number: int,
    ) -> list[ConversationStep]:
        """Get steps for a specific round."""
        result = await db.execute(
            select(ConversationStep)
            .where(
                ConversationStep.conversation_id == conversation_id,
                ConversationStep.round_number == round_number,
            )
            .order_by(ConversationStep.step_order.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_user_message_by_client_id(
        db: AsyncSession,
        conversation_id: int,
        client_message_id: str,
    ) -> ConversationStep | None:
        """Sub-req 3: lookup a user_message step by its client-supplied
        idempotency key, scoped to one conversation. Used by the engine to
        detect retried submissions and force-enable the resume path so we
        don't accidentally create a duplicate user message + LLM round.
        """
        result = await db.execute(
            select(ConversationStep)
            .where(
                ConversationStep.conversation_id == conversation_id,
                ConversationStep.client_message_id == client_message_id,
                ConversationStep.step_type == "user_message",
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_max_step_order(
        db: AsyncSession, conversation_id: int
    ) -> int:
        """Get the current maximum step_order for a conversation."""
        result = await db.execute(
            select(func.coalesce(func.max(ConversationStep.step_order), 0)).where(
                ConversationStep.conversation_id == conversation_id
            )
        )
        return result.scalar_one()

    @staticmethod
    async def count_by_conversation(
        db: AsyncSession, conversation_id: int
    ) -> int:
        result = await db.execute(
            select(func.count()).select_from(ConversationStep).where(
                ConversationStep.conversation_id == conversation_id
            )
        )
        return result.scalar_one()

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> ConversationStep:
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")
        item = ConversationStep(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: ConversationStep, data: dict
    ) -> ConversationStep:
        if "metadata" in data:
            data["metadata_"] = data.pop("metadata")
        for key, value in data.items():
            if hasattr(item, key) and value is not None:
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item
