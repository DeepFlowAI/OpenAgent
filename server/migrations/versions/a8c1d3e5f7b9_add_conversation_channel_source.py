"""add conversation channel source

Revision ID: a8c1d3e5f7b9
Revises: f2a4b6c8d0e1
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a8c1d3e5f7b9"
down_revision: Union[str, None] = "f2a4b6c8d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("channel_source", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "channel_source")
