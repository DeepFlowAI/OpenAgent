"""
Unit tests for ConversationReportService

Covers the pure logic that does not require a database:
- range validation
- percentage calculation
- bucket generation and gap filling
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.exceptions import ValidationError
from app.models.conversation import Conversation
from app.repositories.conversation_report_repository import (
    ConversationReportRepository,
    _granularity_trunc,
)
from app.services.conversation_report_service import (
    ConversationReportService,
    _generate_buckets,
    _percentage,
    _truncate,
    _validate_range,
)


UTC = timezone.utc


class _EmptyRows:
    def all(self):
        return []


class TestGranularityTruncSql:
    """Compile-time smoke tests for the bucket SQL — catches regressions in the
    half_hour epoch math (which can't otherwise be exercised without a DB).
    """

    def _compile(self, granularity: str) -> str:
        expr = _granularity_trunc(Conversation.started_at, granularity)
        q = select(expr.label("ts"))
        return str(q.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    def test_half_hour_uses_utc_epoch_math(self):
        sql = self._compile("half_hour")
        assert "interval" not in sql.lower()
        assert "to_timestamp" in sql
        assert "floor" in sql
        assert "1800" in sql
        assert "timezone" in sql.lower()

    def test_hour_uses_utc_epoch_math(self):
        sql = self._compile("hour")
        assert "3600" in sql
        assert "to_timestamp" in sql
        assert "timezone" in sql.lower()
        assert "date_trunc('hour'" not in sql

    def test_day_uses_utc_epoch_math(self):
        sql = self._compile("day")
        assert "86400" in sql
        assert "timezone" in sql.lower()

    def test_month_uses_utc_date_trunc(self):
        sql = self._compile("month")
        assert "date_trunc('month'" in sql
        assert "timezone" in sql.lower()

    def test_unknown_granularity_raises(self):
        with pytest.raises(ValueError):
            _granularity_trunc(Conversation.started_at, "year")


class TestConversationReportRepositorySql:

    @pytest.mark.asyncio
    async def test_trend_message_query_filters_conversation_started_at(self):
        mock_db = AsyncMock()
        mock_db.execute.side_effect = [_EmptyRows(), _EmptyRows()]

        await ConversationReportRepository.fetch_trend(
            mock_db,
            "T1",
            42,
            datetime(2026, 5, 19, tzinfo=UTC),
            datetime(2026, 5, 20, tzinfo=UTC),
            "hour",
        )

        message_query = mock_db.execute.await_args_list[1].args[0]
        sql = str(message_query.compile(dialect=postgresql.dialect()))

        assert "conversations.started_at >= " in sql
        assert "conversations.started_at < " in sql
        assert "conversation_steps.created_at >= " in sql
        assert "conversation_steps.created_at < " in sql


class TestPercentage:

    def test_zero_denominator_returns_none(self):
        assert _percentage(5, 0) is None

    def test_normal_case_returns_one_decimal(self):
        assert _percentage(312, 456) == 68.4

    def test_zero_numerator_returns_zero(self):
        assert _percentage(0, 100) == 0.0

    def test_full_returns_100(self):
        assert _percentage(50, 50) == 100.0


class TestValidateRange:

    def test_missing_one_end_raises(self):
        with pytest.raises(ValidationError):
            _validate_range(None, datetime(2026, 5, 19, tzinfo=UTC))

    def test_start_after_end_raises(self):
        with pytest.raises(ValidationError):
            _validate_range(
                datetime(2026, 5, 20, tzinfo=UTC),
                datetime(2026, 5, 19, tzinfo=UTC),
            )

    def test_equal_start_and_end_raises(self):
        ts = datetime(2026, 5, 19, tzinfo=UTC)
        with pytest.raises(ValidationError):
            _validate_range(ts, ts)

    def test_range_exceeds_366_days_raises(self):
        with pytest.raises(ValidationError):
            _validate_range(
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2026, 3, 1, tzinfo=UTC),  # 424 days
            )

    def test_naive_datetime_is_treated_as_utc(self):
        a = datetime(2026, 5, 12, 14, 32, 10)
        b = datetime(2026, 5, 19, 14, 32, 10)
        result_a, result_b = _validate_range(a, b)
        assert result_a.tzinfo is not None
        assert result_b.tzinfo is not None

    def test_valid_seven_days_passes(self):
        a = datetime(2026, 5, 12, tzinfo=UTC)
        b = datetime(2026, 5, 19, tzinfo=UTC)
        result_a, result_b = _validate_range(a, b)
        assert result_a == a and result_b == b


class TestTruncate:

    def test_half_hour_buckets_to_lower_30(self):
        assert _truncate(
            datetime(2026, 5, 19, 14, 47, 30, tzinfo=UTC), "half_hour"
        ) == datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)
        assert _truncate(
            datetime(2026, 5, 19, 14, 5, 0, tzinfo=UTC), "half_hour"
        ) == datetime(2026, 5, 19, 14, 0, 0, tzinfo=UTC)

    def test_hour_truncates_minutes(self):
        assert _truncate(
            datetime(2026, 5, 19, 14, 47, tzinfo=UTC), "hour"
        ) == datetime(2026, 5, 19, 14, 0, tzinfo=UTC)

    def test_day_truncates_to_midnight(self):
        assert _truncate(
            datetime(2026, 5, 19, 14, 47, tzinfo=UTC), "day"
        ) == datetime(2026, 5, 19, 0, 0, tzinfo=UTC)

    def test_month_truncates_to_first_day(self):
        assert _truncate(
            datetime(2026, 5, 19, 14, 47, tzinfo=UTC), "month"
        ) == datetime(2026, 5, 1, 0, 0, tzinfo=UTC)


class TestGenerateBuckets:

    def test_hour_buckets_over_3_hours(self):
        ticks = _generate_buckets(
            datetime(2026, 5, 19, 14, 0, tzinfo=UTC),
            datetime(2026, 5, 19, 17, 0, tzinfo=UTC),
            "hour",
        )
        assert ticks == [
            datetime(2026, 5, 19, 14, 0, tzinfo=UTC),
            datetime(2026, 5, 19, 15, 0, tzinfo=UTC),
            datetime(2026, 5, 19, 16, 0, tzinfo=UTC),
        ]

    def test_half_hour_buckets_over_90_minutes(self):
        ticks = _generate_buckets(
            datetime(2026, 5, 19, 14, 0, tzinfo=UTC),
            datetime(2026, 5, 19, 15, 30, tzinfo=UTC),
            "half_hour",
        )
        assert ticks == [
            datetime(2026, 5, 19, 14, 0, tzinfo=UTC),
            datetime(2026, 5, 19, 14, 30, tzinfo=UTC),
            datetime(2026, 5, 19, 15, 0, tzinfo=UTC),
        ]

    def test_hour_buckets_span_multiple_days(self):
        ticks = _generate_buckets(
            datetime(2026, 5, 19, 22, 0, tzinfo=UTC),
            datetime(2026, 5, 21, 2, 0, tzinfo=UTC),
            "hour",
        )
        assert len(ticks) == 28
        assert ticks[0] == datetime(2026, 5, 19, 22, 0, tzinfo=UTC)
        assert ticks[2] == datetime(2026, 5, 20, 0, 0, tzinfo=UTC)
        assert ticks[-1] == datetime(2026, 5, 21, 1, 0, tzinfo=UTC)

    def test_day_buckets_over_3_days(self):
        ticks = _generate_buckets(
            datetime(2026, 5, 17, 0, 0, tzinfo=UTC),
            datetime(2026, 5, 20, 0, 0, tzinfo=UTC),
            "day",
        )
        assert ticks == [
            datetime(2026, 5, 17, tzinfo=UTC),
            datetime(2026, 5, 18, tzinfo=UTC),
            datetime(2026, 5, 19, tzinfo=UTC),
        ]

    def test_month_buckets_wraps_year(self):
        ticks = _generate_buckets(
            datetime(2025, 11, 1, tzinfo=UTC),
            datetime(2026, 2, 1, tzinfo=UTC),
            "month",
        )
        assert ticks == [
            datetime(2025, 11, 1, tzinfo=UTC),
            datetime(2025, 12, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ]


class TestGetOverview:

    @pytest.mark.asyncio
    async def test_computes_rates_and_passes_counts_through(self):
        mock_db = AsyncMock()
        with patch(
            "app.services.conversation_report_service.ConversationReportRepository"
        ) as mock_repo:
            mock_repo.fetch_overview = AsyncMock(return_value={
                "session_count": 1248,
                "effective_session_count": 986,
                "user_message_count": 4320,
                "agent_message_count": 3856,
                "like_count": 312,
                "dislike_count": 144,
            })
            result = await ConversationReportService.get_overview(
                mock_db,
                "T1",
                42,
                datetime(2026, 5, 12, tzinfo=UTC),
                datetime(2026, 5, 19, tzinfo=UTC),
            )

        assert result["session_count"] == 1248
        # 3856 / 4320 = 89.259... → 89.3
        assert result["reply_rate"] == 89.3
        # 312 / (312+144) = 68.42... → 68.4
        assert result["like_rate"] == 68.4
        # 144 / 456 = 31.57... → 31.6
        assert result["dislike_rate"] == 31.6

    @pytest.mark.asyncio
    async def test_reply_rate_none_when_no_user_messages(self):
        mock_db = AsyncMock()
        with patch(
            "app.services.conversation_report_service.ConversationReportRepository"
        ) as mock_repo:
            mock_repo.fetch_overview = AsyncMock(return_value={
                "session_count": 0,
                "effective_session_count": 0,
                "user_message_count": 0,
                "agent_message_count": 0,
                "like_count": 0,
                "dislike_count": 0,
            })
            result = await ConversationReportService.get_overview(
                mock_db,
                "T1",
                42,
                datetime(2026, 5, 12, tzinfo=UTC),
                datetime(2026, 5, 19, tzinfo=UTC),
            )

        assert result["reply_rate"] is None
        assert result["like_rate"] is None
        assert result["dislike_rate"] is None


class TestGetTrend:

    @pytest.mark.asyncio
    async def test_fills_missing_buckets_with_zero(self):
        # Range: 14:00 to 17:00, hour granularity → 3 buckets expected
        # Repo returns only 14:00 with data; 15:00 and 16:00 should be 0-filled
        mock_db = AsyncMock()
        with patch(
            "app.services.conversation_report_service.ConversationReportRepository"
        ) as mock_repo:
            mock_repo.fetch_trend = AsyncMock(return_value={
                datetime(2026, 5, 19, 14, 0, tzinfo=UTC): {
                    "session_count": 12,
                    "effective_session_count": 10,
                    "user_message_count": 48,
                    "agent_message_count": 42,
                    "like_count": 3,
                    "dislike_count": 1,
                }
            })
            result = await ConversationReportService.get_trend(
                mock_db,
                "T1",
                42,
                datetime(2026, 5, 19, 14, 0, tzinfo=UTC),
                datetime(2026, 5, 19, 17, 0, tzinfo=UTC),
                "hour",
            )

        assert result["granularity"] == "hour"
        assert len(result["buckets"]) == 3

        first = result["buckets"][0]
        assert first["session_count"] == 12
        assert first["reply_rate"] == 87.5  # 42 / 48
        assert first["like_rate"] == 75.0  # 3 / (3+1)
        assert first["dislike_rate"] == 25.0

        second = result["buckets"][1]
        assert second["session_count"] == 0
        assert second["user_message_count"] == 0
        assert second["reply_rate"] is None  # 0 user messages
        assert second["like_rate"] is None

    @pytest.mark.asyncio
    async def test_same_clock_hour_on_different_days_stay_separate(self):
        mock_db = AsyncMock()
        with patch(
            "app.services.conversation_report_service.ConversationReportRepository"
        ) as mock_repo:
            mock_repo.fetch_trend = AsyncMock(return_value={
                datetime(2026, 5, 19, 14, 0, tzinfo=UTC): {
                    "session_count": 1,
                    "effective_session_count": 1,
                    "user_message_count": 1,
                    "agent_message_count": 0,
                    "like_count": 0,
                    "dislike_count": 0,
                },
                datetime(2026, 5, 20, 14, 0, tzinfo=UTC): {
                    "session_count": 2,
                    "effective_session_count": 2,
                    "user_message_count": 2,
                    "agent_message_count": 0,
                    "like_count": 0,
                    "dislike_count": 0,
                },
            })
            result = await ConversationReportService.get_trend(
                mock_db,
                "T1",
                42,
                datetime(2026, 5, 19, 0, 0, tzinfo=UTC),
                datetime(2026, 5, 21, 0, 0, tzinfo=UTC),
                "hour",
            )

        assert len(result["buckets"]) == 48
        active = [b for b in result["buckets"] if b["session_count"] > 0]
        assert len(active) == 2
        assert {b["session_count"] for b in active} == {1, 2}
        assert sum(b["session_count"] for b in result["buckets"]) == 3

    @pytest.mark.asyncio
    async def test_empty_result_returns_zero_filled_range(self):
        mock_db = AsyncMock()
        with patch(
            "app.services.conversation_report_service.ConversationReportRepository"
        ) as mock_repo:
            mock_repo.fetch_trend = AsyncMock(return_value={})
            result = await ConversationReportService.get_trend(
                mock_db,
                "T1",
                42,
                datetime(2026, 5, 19, 14, 0, tzinfo=UTC),
                datetime(2026, 5, 19, 16, 0, tzinfo=UTC),
                "hour",
            )

        assert len(result["buckets"]) == 2
        assert all(b["session_count"] == 0 for b in result["buckets"])
        assert all(b["reply_rate"] is None for b in result["buckets"])
