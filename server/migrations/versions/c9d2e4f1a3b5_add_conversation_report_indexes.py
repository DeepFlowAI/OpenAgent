"""add conversation report covering indexes

Revision ID: c9d2e4f1a3b5
Revises: b1c2d3e4f5a6
Create Date: 2026-05-19

Indexes added to support /api/v1/agents/{id}/conversation-report/{overview,trend}
aggregation queries on `conversations` + `conversation_steps`. All three are
partial indexes — they keep the index footprint small by only covering rows
that the report actually scans.

If applying on a production table with significant data, drop these statements
into a `psql` session and recreate with `CREATE INDEX CONCURRENTLY` to avoid
the brief AccessExclusiveLock that `op.create_index` takes — the report
queries themselves are read-only and safe to deploy alongside, but the lock
window can block writes for a few seconds on large `conversation_steps`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c9d2e4f1a3b5"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Conversations: narrow to (tenant, agent, started_at) excluding test
    #    conversations. Used by both overview/trend "session by started_at"
    #    queries when the time window is narrow relative to the agent's history.
    op.create_index(
        "ix_conversations_report",
        "conversations",
        ["tenant_id", "agent_id", "started_at"],
        unique=False,
        postgresql_where=sa.text(
            "is_test = false AND source IN ('websdk', 'api')"
        ),
    )

    # 2) Conversation steps: covering index for message-level aggregations.
    #    The `INCLUDE (feedback_rating)` clause makes like/dislike counts
    #    index-only scans — no heap fetch required.
    #    Partial WHERE restricts the index to the two step types the report
    #    actually counts, keeping the index ~50% smaller than a full index
    #    (llm_call and tool_call are excluded).
    op.execute(
        sa.text(
            """
            CREATE INDEX ix_steps_report
              ON conversation_steps (conversation_id, step_type, created_at)
              INCLUDE (feedback_rating)
              WHERE step_type IN ('user_message', 'assistant_message')
            """
        )
    )

    # 3) Steps: time-range scan for feedback events. Useful when a tenant has
    #    very high assistant_message volume but very few liked/disliked rows —
    #    this index is ~1% the size of #2 and lets the planner skip directly
    #    to the rated rows.
    op.create_index(
        "ix_steps_feedback_created",
        "conversation_steps",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text(
            "feedback_rating IN ('like', 'dislike')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_steps_feedback_created",
        table_name="conversation_steps",
        postgresql_where=sa.text("feedback_rating IN ('like', 'dislike')"),
    )
    op.execute(sa.text("DROP INDEX IF EXISTS ix_steps_report"))
    op.drop_index(
        "ix_conversations_report",
        table_name="conversations",
        postgresql_where=sa.text(
            "is_test = false AND source IN ('websdk', 'api')"
        ),
    )
