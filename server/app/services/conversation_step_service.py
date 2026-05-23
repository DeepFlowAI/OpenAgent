"""
ConversationStep service — business logic for conversation execution log
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.channel import Channel
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.conversation_step_repository import ConversationStepRepository
from app.schemas.conversation_step import StepCreate, StepFeedbackSubmit, StepUpdate


def _step_to_response_dict(step) -> dict:
    return {
        c.key: getattr(step, "metadata_" if c.key == "metadata" else c.key)
        for c in step.__table__.columns
    }


class ConversationStepService:

    # End-user views hide both transient and abandoned states. ``pending``
    # is the placeholder assistant_message a round opens with — it has no
    # content yet, so showing it produces empty bubbles in the UI. Once the
    # round commits to ``success`` (or is salvaged as ``incomplete`` after
    # a stream failure), the row reappears in the timeline normally.
    _USER_HIDDEN_STATUSES = frozenset({"pending", "incomplete"})

    @staticmethod
    def _feedback_enabled(channel: Channel) -> bool:
        config = channel.config or {}
        behavior = config.get("behavior")
        return isinstance(behavior, dict) and behavior.get("feedbackEnabled") is True

    @staticmethod
    async def get_timeline(
        db: AsyncSession,
        conversation_id: int,
        *,
        include_incomplete: bool = True,
    ) -> dict:
        """Get the full conversation timeline (lightweight, for left panel rendering).

        ``include_incomplete`` (sub-req 2/4): admin/log views pass True
        (default) to keep both ``pending`` (in-flight) and ``incomplete``
        (abandoned partial) steps visible for debugging. End-user chat
        history reconstruction passes False so neither a still-streaming
        round nor a discarded "phantom round" from a network failure leaks
        into the rebuilt UI.
        """
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found")

        steps = await ConversationStepRepository.get_timeline(db, conversation_id)
        if not include_incomplete:
            hidden = ConversationStepService._USER_HIDDEN_STATUSES
            steps = [
                s for s in steps
                if (s.get("status") if hasattr(s, "get") else s["status"]) not in hidden
            ]
        return {
            "conversation_id": conversation_id,
            "steps": steps,
            "total_steps": len(steps),
        }

    @staticmethod
    async def get_step_detail(
        db: AsyncSession,
        step_id: int,
    ):
        """Get full step detail including large fields (for LLM modal).
        For llm_call steps, also fetches child tool_call steps.
        If no direct children, falls back to same-round tool_call steps."""
        item = await ConversationStepRepository.get_by_id(db, step_id)
        if not item:
            raise NotFoundError("Step not found")

        if item.step_type == "llm_call":
            children = await ConversationStepRepository.get_children(db, step_id)
            if not children:
                children = await ConversationStepRepository.get_round_tool_calls(
                    db, item.conversation_id, item.round_number,
                )
            return {
                **_step_to_response_dict(item),
                "tool_call_steps": children,
            }

        return item

    @staticmethod
    async def create_step(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: str,
        data: StepCreate,
    ):
        """Create a new step and update conversation counters accordingly."""
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found")

        max_order = await ConversationStepRepository.get_max_step_order(
            db, conversation_id
        )

        step_data = data.model_dump()
        step_data["conversation_id"] = conversation_id
        step_data["tenant_id"] = tenant_id
        step_data["step_order"] = max_order + 1

        step = await ConversationStepRepository.create(db, step_data)

        # Update conversation denormalized counters
        counter_updates = {}
        if data.step_type == "llm_call":
            counter_updates["llm_call_count"] = 1
            if data.input_tokens:
                counter_updates["input_tokens"] = data.input_tokens
            if data.output_tokens:
                counter_updates["output_tokens"] = data.output_tokens
            if data.total_tokens:
                counter_updates["total_tokens"] = data.total_tokens
        elif data.step_type == "tool_call":
            counter_updates["tool_call_count"] = 1
        elif data.step_type == "assistant_message":
            counter_updates["round_count"] = 1

        if counter_updates:
            await ConversationRepository.increment_counters(
                db, conversation_id, **counter_updates
            )

        # Auto-set conversation title from first user message
        if data.step_type == "user_message" and not conversation.title and data.content:
            title = data.content[:200]
            await ConversationRepository.update(
                db, conversation, {"title": title}
            )

        return step

    @staticmethod
    async def update_step(
        db: AsyncSession,
        step_id: int,
        conversation_id: int,
        data: StepUpdate,
    ):
        """Update an existing step (e.g. LLM response arrives) and sync counters."""
        item = await ConversationStepRepository.get_by_id(db, step_id)
        if not item:
            raise NotFoundError("Step not found")

        update_data = data.model_dump(exclude_unset=True)
        step = await ConversationStepRepository.update(db, item, update_data)

        # If LLM call tokens are being updated, sync to conversation
        if item.step_type == "llm_call":
            token_updates = {}
            if data.input_tokens is not None:
                token_updates["input_tokens"] = data.input_tokens
            if data.output_tokens is not None:
                token_updates["output_tokens"] = data.output_tokens
            if data.total_tokens is not None:
                token_updates["total_tokens"] = data.total_tokens
            if token_updates:
                await ConversationRepository.increment_counters(
                    db, conversation_id, **token_updates
                )

        return step

    @staticmethod
    async def submit_public_feedback(
        db: AsyncSession,
        *,
        channel: Channel,
        step_id: int,
        data: StepFeedbackSubmit,
    ) -> dict:
        """Submit or overwrite visitor feedback for one assistant reply step."""
        if not channel.agent_id:
            raise NotFoundError("Channel has no agent bound")
        if not ConversationStepService._feedback_enabled(channel):
            raise ValidationError("Feedback is disabled for this channel")

        step = await ConversationStepRepository.get_by_id(db, step_id)
        if not step or step.tenant_id != channel.tenant_id:
            raise NotFoundError("Step not found")
        if step.step_type != "assistant_message":
            raise ValidationError("Feedback can only be submitted for assistant messages")
        if step.status != "success" or not (step.content or "").strip():
            raise ValidationError("Feedback can only be submitted for completed replies")

        conversation = await ConversationRepository.get_by_id(db, step.conversation_id)
        if (
            not conversation
            or conversation.tenant_id != channel.tenant_id
            or conversation.agent_id != channel.agent_id
        ):
            raise NotFoundError("Step not found")

        comment = data.comment.strip() if data.comment else None
        if comment == "":
            comment = None

        updated = await ConversationStepRepository.update_feedback(
            db,
            step,
            rating=data.rating,
            comment=comment,
            updated_at=datetime.now(timezone.utc),
        )
        return {
            "step_id": updated.id,
            "feedback_rating": updated.feedback_rating,
            "feedback_comment": updated.feedback_comment,
            "feedback_updated_at": updated.feedback_updated_at,
        }
