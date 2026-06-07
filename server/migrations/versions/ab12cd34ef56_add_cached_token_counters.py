"""add cached token counters

Revision ID: ab12cd34ef56
Revises: c9d2e4f1a3b5
Create Date: 2026-05-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ab12cd34ef56"
down_revision: Union[str, None] = "c9d2e4f1a3b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "total_cached_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "conversation_steps",
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_steps", "cached_tokens")
    op.drop_column("conversations", "total_cached_tokens")
