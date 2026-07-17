"""add knowledge base qas

Revision ID: b6c7d8e9f0a1
Revises: a4b5c6d7e8f9
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("source_type", sa.String(length=16), server_default="git", nullable=False),
    )
    op.create_check_constraint(
        "ck_documents_source_type", "documents", "source_type IN ('git', 'qa')"
    )
    op.create_index(
        "ix_documents_kb_source_type",
        "documents",
        ["knowledge_base_id", "source_type"],
        unique=False,
    )
    op.create_table(
        "knowledge_base_qas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("answer_markdown", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "access_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("process_status", sa.String(length=16), server_default="processing", nullable=False),
        sa.Column("process_error", sa.Text(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("process_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "process_status IN ('processing', 'ready', 'failed')",
            name="ck_kb_qas_process_status",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_kb_qas_document_id"),
        sa.UniqueConstraint(
            "knowledge_base_id", "question", name="uq_kb_qas_kb_question"
        ),
    )
    op.create_index(
        "ix_kb_qas_tenant_kb_updated",
        "knowledge_base_qas",
        ["tenant_id", "knowledge_base_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_kb_qas_tenant_kb_updated", table_name="knowledge_base_qas")
    op.drop_table("knowledge_base_qas")
    op.drop_index("ix_documents_kb_source_type", table_name="documents")
    op.drop_constraint("ck_documents_source_type", "documents", type_="check")
    op.drop_column("documents", "source_type")
