"""
Unit tests for visitor feedback on conversation steps.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.schemas.conversation_step import StepFeedbackSubmit
from app.services.conversation_service import ConversationService
from app.services.conversation_step_service import ConversationStepService


def _channel(enabled: bool = True):
    return SimpleNamespace(
        id=5,
        tenant_id="T_TEST_001",
        agent_id=7,
        config={"behavior": {"feedbackEnabled": enabled}},
    )


def _assistant_step(**overrides):
    base = {
        "id": 11,
        "tenant_id": "T_TEST_001",
        "conversation_id": 23,
        "round_number": 1,
        "step_order": 3,
        "step_type": "assistant_message",
        "content": "Hello",
        "status": "success",
        "created_at": datetime(2026, 5, 15, tzinfo=timezone.utc),
        "feedback_rating": None,
        "feedback_comment": None,
        "feedback_updated_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestConversationStepFeedbackService:

    @pytest.mark.asyncio
    async def test_submit_public_feedback_updates_assistant_step(self):
        db = AsyncMock()
        step = _assistant_step()
        conversation = SimpleNamespace(
            tenant_id="T_TEST_001",
            agent_id=7,
        )

        async def update_feedback(_db, item, *, rating, comment, updated_at):
            item.feedback_rating = rating
            item.feedback_comment = comment
            item.feedback_updated_at = updated_at
            return item

        with (
            patch("app.services.conversation_step_service.ConversationStepRepository") as step_repo,
            patch("app.services.conversation_step_service.ConversationRepository") as conv_repo,
        ):
            step_repo.get_by_id = AsyncMock(return_value=step)
            step_repo.update_feedback = AsyncMock(side_effect=update_feedback)
            conv_repo.get_by_id = AsyncMock(return_value=conversation)

            result = await ConversationStepService.submit_public_feedback(
                db,
                channel=_channel(),
                step_id=step.id,
                data=StepFeedbackSubmit(rating="like", comment="  useful  "),
            )

        assert result["step_id"] == step.id
        assert result["feedback_rating"] == "like"
        assert result["feedback_comment"] == "useful"
        assert result["feedback_updated_at"] is not None
        step_repo.update_feedback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_public_feedback_rejects_disabled_channel(self):
        with pytest.raises(ValidationError, match="Feedback is disabled"):
            await ConversationStepService.submit_public_feedback(
                AsyncMock(),
                channel=_channel(enabled=False),
                step_id=11,
                data=StepFeedbackSubmit(rating="like", comment=None),
            )

    @pytest.mark.asyncio
    async def test_submit_public_feedback_rejects_non_assistant_step(self):
        with (
            patch("app.services.conversation_step_service.ConversationStepRepository") as step_repo,
            patch("app.services.conversation_step_service.ConversationRepository") as conv_repo,
        ):
            step_repo.get_by_id = AsyncMock(
                return_value=_assistant_step(step_type="user_message")
            )
            conv_repo.get_by_id = AsyncMock()

            with pytest.raises(ValidationError, match="assistant messages"):
                await ConversationStepService.submit_public_feedback(
                    AsyncMock(),
                    channel=_channel(),
                    step_id=11,
                    data=StepFeedbackSubmit(rating="dislike", comment=None),
                )

        conv_repo.get_by_id.assert_not_called()

    def test_feedback_comment_max_length_is_validated(self):
        with pytest.raises(PydanticValidationError):
            StepFeedbackSubmit(rating="like", comment="x" * 501)

    def test_export_rows_include_feedback_fields(self):
        conversation = SimpleNamespace(
            external_id="conv_test",
            id=23,
            started_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
        )
        steps = [
            _assistant_step(
                id=1,
                step_type="user_message",
                step_order=1,
                content="Question",
                client_message_id="msg-1",
            ),
            _assistant_step(
                id=2,
                step_type="assistant_message",
                step_order=2,
                content="Answer",
                feedback_rating="dislike",
                feedback_comment="Needs sources",
            ),
        ]

        rows = ConversationService._build_export_rows(conversation, steps)

        assert rows[0][9] == "Answer"
        assert rows[0][10] == "踩"
        assert rows[0][11] == "Needs sources"
