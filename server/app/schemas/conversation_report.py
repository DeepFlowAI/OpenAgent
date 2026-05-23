"""
Conversation Report Pydantic schemas

Read-only aggregation endpoints for the per-agent 会话报表 page.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Time granularity for trend buckets
TrendGranularity = Literal["half_hour", "hour", "day", "month"]

# Maximum allowed query range, in days
MAX_RANGE_DAYS = 366


class ConversationReportOverviewResponse(BaseModel):
    """Aggregated counts and rates for the selected time range."""
    model_config = ConfigDict(from_attributes=True)

    session_count: int
    effective_session_count: int
    user_message_count: int
    agent_message_count: int
    # Percentage value (e.g. 89.3 means 89.3%); null when denominator is 0
    reply_rate: float | None
    like_count: int
    dislike_count: int
    like_rate: float | None
    dislike_rate: float | None


class ConversationReportTrendBucket(BaseModel):
    """One time bucket on the trend timeline."""
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    session_count: int
    effective_session_count: int
    user_message_count: int
    agent_message_count: int
    like_count: int
    dislike_count: int
    reply_rate: float | None
    like_rate: float | None
    dislike_rate: float | None


class ConversationReportTrendResponse(BaseModel):
    """Trend response: full list of contiguous buckets in [from, to)."""
    model_config = ConfigDict(from_attributes=True)

    granularity: TrendGranularity
    buckets: list[ConversationReportTrendBucket]
