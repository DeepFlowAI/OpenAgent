from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.conversation_step import ConversationStep
from app.schemas.conversation_step import StepDetailResponse, StepTimelineItem
from app.services.conversation_step_service import ConversationStepService


def _step(**overrides):
    data = {
        "id": 101,
        "conversation_id": 42,
        "tenant_id": "T_TEST_001",
        "round_number": 1,
        "step_order": 2,
        "step_type": "llm_call",
        "status": "success",
        "metadata_": {"stream_retry_count": 1},
        "created_at": datetime(2026, 5, 17, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return ConversationStep(**data)


def test_step_detail_response_reads_orm_metadata_alias():
    detail = StepDetailResponse.model_validate(_step(cached_tokens=12))

    assert detail.metadata == {"stream_retry_count": 1}
    assert detail.cached_tokens == 12


def test_timeline_item_reads_orm_metadata_alias():
    item = StepTimelineItem.model_validate(_step(cached_tokens=12))

    assert item.metadata == {"stream_retry_count": 1}
    assert item.cached_tokens == 12


@pytest.mark.asyncio
async def test_llm_step_detail_returns_json_metadata():
    step = _step()

    with patch("app.services.conversation_step_service.ConversationStepRepository") as repo:
        repo.get_by_id = AsyncMock(return_value=step)
        repo.get_children = AsyncMock(return_value=[])
        repo.get_round_tool_calls = AsyncMock(return_value=[])

        result = await ConversationStepService.get_step_detail(AsyncMock(), step.id)

    detail = StepDetailResponse.model_validate(result)

    assert result["metadata"] == {"stream_retry_count": 1}
    assert detail.metadata == {"stream_retry_count": 1}
