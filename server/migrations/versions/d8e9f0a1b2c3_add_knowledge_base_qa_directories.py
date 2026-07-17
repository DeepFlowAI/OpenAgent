"""add knowledge base qa directories

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-07-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_base_qa_directories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("sort_order >= 0", name="ck_kb_qa_dirs_sort_order"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["knowledge_base_qa_directories.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_base_id",
            "parent_id",
            "name",
            name="uq_kb_qa_dirs_parent_name",
        ),
    )
    op.create_index(
        "ix_kb_qa_dirs_tenant_kb_parent_sort",
        "knowledge_base_qa_directories",
        ["tenant_id", "knowledge_base_id", "parent_id", "sort_order"],
        unique=False,
    )
    op.create_index(
        "uq_kb_qa_dirs_root_name",
        "knowledge_base_qa_directories",
        ["knowledge_base_id", "name"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_kb_qa_dirs_root_name", table_name="knowledge_base_qa_directories"
    )
    op.drop_index(
        "ix_kb_qa_dirs_tenant_kb_parent_sort",
        table_name="knowledge_base_qa_directories",
    )
    op.drop_table("knowledge_base_qa_directories")
