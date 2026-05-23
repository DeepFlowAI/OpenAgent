"""add conversation channel id

Revision ID: 9f4a7c2d8b10
Revises: a8c1d3e5f7b9
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9f4a7c2d8b10"
down_revision: Union[str, None] = "a8c1d3e5f7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "conversations",
        "source",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.add_column(
        "conversations",
        sa.Column("channel_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_conversations_channel_id",
        "conversations",
        ["channel_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_conversations_channel_id_channels",
        "conversations",
        "channels",
        ["channel_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_conversations_channel_id_channels",
        "conversations",
        type_="foreignkey",
    )
    op.drop_index("ix_conversations_channel_id", table_name="conversations")
    op.drop_column("conversations", "channel_id")
    op.alter_column(
        "conversations",
        "source",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
