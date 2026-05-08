"""add tenant slug

Revision ID: b7c9d2e4f1a3
Revises: aa0ffb9fef05
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7c9d2e4f1a3"
down_revision: Union[str, None] = "aa0ffb9fef05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("slug", sa.String(length=64), nullable=True))
    op.create_index("uq_tenants_slug", "tenants", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_tenants_slug", table_name="tenants")
    op.drop_column("tenants", "slug")
