"""add agent message preprocessing rules

Revision ID: e6a2b4c8d9f0
Revises: d5f1a7c9e2b0
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e6a2b4c8d9f0"
down_revision: Union[str, None] = "d5f1a7c9e2b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_message_preprocessing_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("condition", sa.String(length=1000), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("value", sa.String(length=500), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "action IN ('prefix', 'suffix')",
            name="ck_agent_msg_pre_rules_action",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_msg_pre_rules_agent_id_id",
        "agent_message_preprocessing_rules",
        ["agent_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_msg_pre_rules_tenant_id",
        "agent_message_preprocessing_rules",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_msg_pre_rules_tenant_id",
        table_name="agent_message_preprocessing_rules",
    )
    op.drop_index(
        "ix_agent_msg_pre_rules_agent_id_id",
        table_name="agent_message_preprocessing_rules",
    )
    op.drop_table("agent_message_preprocessing_rules")
