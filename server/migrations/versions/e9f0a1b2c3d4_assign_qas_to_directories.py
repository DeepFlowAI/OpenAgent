"""assign qas to directories

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-07-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_base_qas",
        sa.Column("directory_id", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        INSERT INTO knowledge_base_qa_directories (
            tenant_id,
            knowledge_base_id,
            parent_id,
            name,
            sort_order,
            created_at,
            updated_at
        )
        SELECT
            MIN(qa.tenant_id),
            qa.knowledge_base_id,
            NULL,
            '未分类',
            COALESCE((
                SELECT MAX(existing.sort_order) + 1
                FROM knowledge_base_qa_directories AS existing
                WHERE existing.knowledge_base_id = qa.knowledge_base_id
                  AND existing.parent_id IS NULL
            ), 0),
            now(),
            now()
        FROM knowledge_base_qas AS qa
        WHERE NOT EXISTS (
            SELECT 1
            FROM knowledge_base_qa_directories AS existing
            WHERE existing.knowledge_base_id = qa.knowledge_base_id
              AND existing.parent_id IS NULL
              AND existing.name = '未分类'
        )
        GROUP BY qa.knowledge_base_id
        """
    )
    op.execute(
        """
        UPDATE knowledge_base_qas AS qa
        SET directory_id = directory.id
        FROM knowledge_base_qa_directories AS directory
        WHERE directory.knowledge_base_id = qa.knowledge_base_id
          AND directory.parent_id IS NULL
          AND directory.name = '未分类'
          AND qa.directory_id IS NULL
        """
    )
    op.alter_column("knowledge_base_qas", "directory_id", nullable=False)
    op.create_foreign_key(
        "fk_kb_qas_directory_id",
        "knowledge_base_qas",
        "knowledge_base_qa_directories",
        ["directory_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_kb_qas_kb_directory",
        "knowledge_base_qas",
        ["knowledge_base_id", "directory_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_kb_qas_kb_directory", table_name="knowledge_base_qas")
    op.drop_constraint(
        "fk_kb_qas_directory_id", "knowledge_base_qas", type_="foreignkey"
    )
    op.drop_column("knowledge_base_qas", "directory_id")
