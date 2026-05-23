"""
Conversation Report repository — aggregation queries for the conversation
report page. Read-only.

Performance notes
-----------------
- All filtering is rooted in a shared `_base_conversation_filter` that the
  partial index ``ix_conversations_report`` covers
  (`tenant_id, agent_id, started_at WHERE is_test=false AND source IN (...)`).
- Message-level queries use ``ix_steps_report``
  (`conversation_id, step_type, created_at INCLUDE feedback_rating`)
  for index-only scans — no heap fetch for like/dislike counts.
- ``fetch_overview`` runs **one** SQL (was 2): conversations LEFT JOIN
  pre-aggregated step counts on `conversation_id`.
- ``fetch_trend`` runs **two** SQL (was 3): sessions-by-bucket and
  messages-by-bucket-with-effective-sessions; FULL OUTER JOIN happens in
  Python so the bucket list ends up sparse but correct.
- ``half_hour`` bucketing uses epoch arithmetic
  (`to_timestamp(floor(epoch/1800)*1800)`) which is portable and avoids
  brittle ``interval`` literal math.
"""
from datetime import datetime
from typing import Literal

from sqlalchemy import and_, case, false, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.conversation_step import ConversationStep
from app.schemas.conversation import SOURCE_API, SOURCE_WEBSDK

INCLUDED_SOURCES = (SOURCE_WEBSDK, SOURCE_API)

Granularity = Literal["half_hour", "hour", "day", "month"]


def _utc_epoch_trunc(column, step_seconds: int):
    """Floor a timestamptz to a UTC bucket start (returns timestamptz)."""
    epoch = func.extract("epoch", column)
    step = literal_column(str(step_seconds))
    bucketed = func.floor(epoch / step) * step
    # Wrap with timezone('UTC', ...) so the bucket key is timestamptz in UTC,
    # not timestamp-without-tz (which would follow the DB session timezone).
    return func.timezone("UTC", func.to_timestamp(bucketed))


def _granularity_trunc(column, granularity: Granularity):
    """Return a SQL expression that floors a timestamp to its bucket start (UTC).

    Each bucket is an absolute instant in the query window (e.g. 2026-05-19
    14:00 UTC and 2026-05-20 14:00 UTC are distinct), not a time-of-day slot
    aggregated across calendar days.
    """
    if granularity == "half_hour":
        return _utc_epoch_trunc(column, 1800)
    if granularity == "hour":
        return _utc_epoch_trunc(column, 3600)
    if granularity == "day":
        return _utc_epoch_trunc(column, 86400)
    if granularity == "month":
        utc_col = func.timezone("UTC", column)
        truncated = func.date_trunc("month", utc_col)
        return func.timezone("UTC", truncated)
    raise ValueError(f"Unsupported granularity: {granularity}")


def _base_conversation_filter(tenant_id: str, agent_id: int):
    """Hard-coded narrowing applied to every report query.

    Matches ``ix_conversations_report`` partial index predicate.
    """
    return and_(
        Conversation.tenant_id == tenant_id,
        Conversation.agent_id == agent_id,
        Conversation.is_test == false(),
        Conversation.source.in_(INCLUDED_SOURCES),
    )


class ConversationReportRepository:

    @staticmethod
    async def fetch_overview(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        started_at_from: datetime,
        started_at_to: datetime,
    ) -> dict:
        """One-shot overview aggregation.

        Structure:
          - inner query: pre-aggregates step counts per conversation_id, filtered
            by step_type IN (...) and created_at in window. Returns one row per
            conversation that has any message in the window.
          - outer query: scans conversations narrowed by the partial index,
            LEFT JOINs the pre-agg, and aggregates counts.

        The LEFT JOIN keeps `session_count` correct for sessions with zero
        messages in the window; the pre-aggregated subquery means each
        conversation is visited at most once per side.
        """
        is_user = ConversationStep.step_type == "user_message"
        is_agent = ConversationStep.step_type == "assistant_message"

        # Sub-aggregate: per-conversation counts within the message window.
        per_conv = (
            select(
                ConversationStep.conversation_id.label("cid"),
                func.count(case((is_user, 1))).label("user_cnt"),
                func.count(case((is_agent, 1))).label("agent_cnt"),
                func.count(
                    case(
                        (
                            and_(is_agent, ConversationStep.feedback_rating == "like"),
                            1,
                        )
                    )
                ).label("like_cnt"),
                func.count(
                    case(
                        (
                            and_(
                                is_agent,
                                ConversationStep.feedback_rating == "dislike",
                            ),
                            1,
                        )
                    )
                ).label("dislike_cnt"),
                func.max(case((is_user, 1), else_=0)).label("has_user_msg"),
            )
            .where(
                ConversationStep.step_type.in_(["user_message", "assistant_message"]),
                ConversationStep.created_at >= started_at_from,
                ConversationStep.created_at < started_at_to,
            )
            .group_by(ConversationStep.conversation_id)
            .subquery()
        )

        q = select(
            func.count().label("session_count"),
            func.coalesce(
                func.sum(case((per_conv.c.has_user_msg == 1, 1))), 0
            ).label("effective_session_count"),
            func.coalesce(func.sum(per_conv.c.user_cnt), 0).label(
                "user_message_count"
            ),
            func.coalesce(func.sum(per_conv.c.agent_cnt), 0).label(
                "agent_message_count"
            ),
            func.coalesce(func.sum(per_conv.c.like_cnt), 0).label("like_count"),
            func.coalesce(func.sum(per_conv.c.dislike_cnt), 0).label(
                "dislike_count"
            ),
        ).select_from(
            Conversation.__table__.outerjoin(
                per_conv, per_conv.c.cid == Conversation.id
            )
        ).where(
            _base_conversation_filter(tenant_id, agent_id),
            Conversation.started_at >= started_at_from,
            Conversation.started_at < started_at_to,
        )

        row = (await db.execute(q)).one()
        return {
            "session_count": int(row.session_count or 0),
            "effective_session_count": int(row.effective_session_count or 0),
            "user_message_count": int(row.user_message_count or 0),
            "agent_message_count": int(row.agent_message_count or 0),
            "like_count": int(row.like_count or 0),
            "dislike_count": int(row.dislike_count or 0),
        }

    @staticmethod
    async def fetch_trend(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        started_at_from: datetime,
        started_at_to: datetime,
        granularity: Granularity,
    ) -> dict[datetime, dict]:
        """Bucket-level aggregation. Returns ``{bucket_start: {...counts}}``.

        Two SQL queries (was three):
          1. session_count keyed by ``started_at`` bucket
          2. message + feedback + effective_session counts keyed by ``created_at``
             bucket (a single GROUP BY collapses Q2+Q3 of the previous impl).

        Service layer fills any missing bucket with zeros.
        """
        base_filter = _base_conversation_filter(tenant_id, agent_id)
        bucket_sessions = _granularity_trunc(Conversation.started_at, granularity)
        bucket_steps = _granularity_trunc(ConversationStep.created_at, granularity)

        # Q1 — session count by `started_at` bucket
        q_sessions = (
            select(
                bucket_sessions.label("ts"),
                func.count().label("session_count"),
            )
            .where(
                base_filter,
                Conversation.started_at >= started_at_from,
                Conversation.started_at < started_at_to,
            )
            .group_by("ts")
        )
        rows_sessions = (await db.execute(q_sessions)).all()

        # Q2 — message + feedback + effective_session counts by `created_at` bucket.
        # `effective_session` is the per-bucket COUNT(DISTINCT conversation_id)
        # over user_message steps, FILTERed by step_type. Same row scan as the
        # message counts — no extra SQL.
        is_user = ConversationStep.step_type == "user_message"
        is_agent = ConversationStep.step_type == "assistant_message"
        q_messages = (
            select(
                bucket_steps.label("ts"),
                func.count(case((is_user, 1))).label("user_message_count"),
                func.count(case((is_agent, 1))).label("agent_message_count"),
                func.count(
                    case(
                        (and_(is_agent, ConversationStep.feedback_rating == "like"), 1)
                    )
                ).label("like_count"),
                func.count(
                    case(
                        (
                            and_(
                                is_agent,
                                ConversationStep.feedback_rating == "dislike",
                            ),
                            1,
                        )
                    )
                ).label("dislike_count"),
                func.count(
                    func.distinct(case((is_user, ConversationStep.conversation_id)))
                ).label("effective_session_count"),
            )
            .select_from(ConversationStep)
            .join(Conversation, Conversation.id == ConversationStep.conversation_id)
            .where(
                base_filter,
                Conversation.started_at >= started_at_from,
                Conversation.started_at < started_at_to,
                ConversationStep.step_type.in_(["user_message", "assistant_message"]),
                ConversationStep.created_at >= started_at_from,
                ConversationStep.created_at < started_at_to,
            )
            .group_by("ts")
        )
        rows_messages = (await db.execute(q_messages)).all()

        # Merge — service layer handles missing-bucket fill
        merged: dict[datetime, dict] = {}
        for r in rows_sessions:
            merged.setdefault(r.ts, _empty_bucket())["session_count"] = int(
                r.session_count or 0
            )
        for r in rows_messages:
            bucket = merged.setdefault(r.ts, _empty_bucket())
            bucket["user_message_count"] = int(r.user_message_count or 0)
            bucket["agent_message_count"] = int(r.agent_message_count or 0)
            bucket["like_count"] = int(r.like_count or 0)
            bucket["dislike_count"] = int(r.dislike_count or 0)
            bucket["effective_session_count"] = int(r.effective_session_count or 0)

        return merged


def _empty_bucket() -> dict:
    return {
        "session_count": 0,
        "effective_session_count": 0,
        "user_message_count": 0,
        "agent_message_count": 0,
        "like_count": 0,
        "dislike_count": 0,
    }
