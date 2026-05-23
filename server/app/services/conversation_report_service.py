"""
Conversation Report service — orchestration, validation, bucket fill,
and percentage computation for the conversation report endpoints.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.repositories.conversation_report_repository import (
    ConversationReportRepository,
)
from app.schemas.conversation_report import MAX_RANGE_DAYS


def _ensure_aware(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validate_range(started_at_from: datetime, started_at_to: datetime) -> tuple[datetime, datetime]:
    """Apply the four range validations from §3.7."""
    if started_at_from is None or started_at_to is None:
        # FastAPI's required-query handling already covers the missing case, but
        # we keep this guard for direct service calls (tests, internal usage).
        raise ValidationError("请同时选择开始与结束时间")

    a = _ensure_aware(started_at_from)
    b = _ensure_aware(started_at_to)

    if a >= b:
        raise ValidationError("开始时间不能晚于结束时间")
    if (b - a).days > MAX_RANGE_DAYS:
        raise ValidationError(f"查询区间不能超过 {MAX_RANGE_DAYS} 天")
    return a, b


def _percentage(numerator: int, denominator: int) -> float | None:
    """Return percentage (e.g. 89.3) with 1 decimal, or None when denom is 0."""
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def _bucket_step(granularity: str) -> timedelta:
    if granularity == "half_hour":
        return timedelta(minutes=30)
    if granularity == "hour":
        return timedelta(hours=1)
    if granularity == "day":
        return timedelta(days=1)
    if granularity == "month":
        # `month` step is variable; we increment day-by-day and date_trunc to
        # month-start when generating ticks below. We won't actually use this
        # return value for month — see _generate_buckets.
        return timedelta(days=28)
    raise ValueError(f"Unsupported granularity: {granularity}")


def _truncate(dt: datetime, granularity: str) -> datetime:
    """Floor a datetime to the start of its bucket (UTC)."""
    if granularity == "half_hour":
        minute = (dt.minute // 30) * 30
        return dt.replace(minute=minute, second=0, microsecond=0)
    if granularity == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "month":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unsupported granularity: {granularity}")


def _next_bucket(ts: datetime, granularity: str) -> datetime:
    if granularity == "month":
        # Add one calendar month
        year = ts.year + (1 if ts.month == 12 else 0)
        month = 1 if ts.month == 12 else ts.month + 1
        return ts.replace(year=year, month=month, day=1)
    return ts + _bucket_step(granularity)


def _generate_buckets(
    started_at_from: datetime, started_at_to: datetime, granularity: str
) -> list[datetime]:
    """Return contiguous bucket-start timestamps in [from, to)."""
    ticks: list[datetime] = []
    current = _truncate(started_at_from, granularity)
    while current < started_at_to:
        ticks.append(current)
        current = _next_bucket(current, granularity)
    return ticks


class ConversationReportService:

    @staticmethod
    async def get_overview(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        started_at_from: datetime,
        started_at_to: datetime,
    ) -> dict:
        a, b = _validate_range(started_at_from, started_at_to)
        raw = await ConversationReportRepository.fetch_overview(
            db, tenant_id, agent_id, a, b
        )
        user = raw["user_message_count"]
        agent = raw["agent_message_count"]
        like = raw["like_count"]
        dislike = raw["dislike_count"]
        feedback_total = like + dislike
        return {
            **raw,
            "reply_rate": _percentage(agent, user),
            "like_rate": _percentage(like, feedback_total),
            "dislike_rate": _percentage(dislike, feedback_total),
        }

    @staticmethod
    async def get_trend(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        started_at_from: datetime,
        started_at_to: datetime,
        granularity: str,
    ) -> dict:
        a, b = _validate_range(started_at_from, started_at_to)
        raw_buckets = await ConversationReportRepository.fetch_trend(
            db, tenant_id, agent_id, a, b, granularity
        )

        # Normalise bucket keys to UTC bucket starts so DB rows align with ticks.
        normalised: dict[datetime, dict] = {}
        for ts, data in raw_buckets.items():
            if not isinstance(ts, datetime):
                continue
            key = _truncate(_ensure_aware(ts), granularity)
            normalised[key] = data

        ticks = _generate_buckets(a, b, granularity)
        result_buckets: list[dict] = []
        for ts in ticks:
            data = normalised.get(ts) or {
                "session_count": 0,
                "effective_session_count": 0,
                "user_message_count": 0,
                "agent_message_count": 0,
                "like_count": 0,
                "dislike_count": 0,
            }
            user = data["user_message_count"]
            agent_msg = data["agent_message_count"]
            feedback_total = data["like_count"] + data["dislike_count"]
            result_buckets.append({
                "ts": ts,
                **data,
                "reply_rate": _percentage(agent_msg, user),
                "like_rate": _percentage(data["like_count"], feedback_total),
                "dislike_rate": _percentage(data["dislike_count"], feedback_total),
            })

        return {
            "granularity": granularity,
            "buckets": result_buckets,
        }
