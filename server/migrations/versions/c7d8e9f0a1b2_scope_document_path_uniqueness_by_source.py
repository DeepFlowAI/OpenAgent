"""scope document path uniqueness by source

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_documents_kb_filepath", "documents", type_="unique"
    )
    op.create_unique_constraint(
        "uq_documents_kb_source_filepath",
        "documents",
        ["knowledge_base_id", "source_type", "file_path"],
    )
    op.execute(
        """
        UPDATE documents AS document
        SET file_path = '_open_agent_sys_qa_/' || qa.id || '.md'
        FROM knowledge_base_qas AS qa
        WHERE qa.document_id = document.id
          AND document.source_type = 'qa'
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_documents_kb_source_filepath", "documents", type_="unique"
    )
    op.create_unique_constraint(
        "uq_documents_kb_filepath",
        "documents",
        ["knowledge_base_id", "file_path"],
    )
