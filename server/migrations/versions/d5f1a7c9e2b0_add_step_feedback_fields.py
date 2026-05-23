"""add step feedback fields

Revision ID: d5f1a7c9e2b0
Revises: c3a1e5f7d9b2
Create Date: 2026-05-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d5f1a7c9e2b0"
down_revision: Union[str, None] = "c3a1e5f7d9b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_steps",
        sa.Column("feedback_rating", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "conversation_steps",
        sa.Column("feedback_comment", sa.Text(), nullable=True),
    )
    op.add_column(
        "conversation_steps",
        sa.Column(
            "feedback_updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("conversation_steps", "feedback_updated_at")
    op.drop_column("conversation_steps", "feedback_comment")
    op.drop_column("conversation_steps", "feedback_rating")
