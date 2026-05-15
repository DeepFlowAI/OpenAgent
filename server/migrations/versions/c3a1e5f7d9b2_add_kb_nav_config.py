"""add knowledge_base nav_config

Revision ID: c3a1e5f7d9b2
Revises: b7c9d2e4f1a3
Create Date: 2026-05-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c3a1e5f7d9b2"
down_revision: Union[str, None] = "b7c9d2e4f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column("nav_config", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "nav_config")
