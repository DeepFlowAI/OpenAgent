"""add conversation step inspections

Revision ID: c1d2e3f4a5b6
Revises: ab12cd34ef56
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table("conversation_step_inspections", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.String(32), nullable=False), sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("step_id", sa.Integer(), sa.ForeignKey("conversation_steps.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("inspector_id", sa.Integer(), sa.ForeignKey("tenant_accounts.id", ondelete="SET NULL")), sa.Column("tag", sa.String(16), nullable=False), sa.Column("issue_types", postgresql.JSONB(), nullable=False, server_default="[]"), sa.Column("issue_description", sa.Text()), sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_step_inspections_tenant_conversation", "conversation_step_inspections", ["tenant_id", "conversation_id"])
    op.create_index("ix_step_inspections_tag", "conversation_step_inspections", ["tag"])
    op.create_table("conversation_step_inspection_histories", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("inspection_id", sa.Integer(), sa.ForeignKey("conversation_step_inspections.id", ondelete="CASCADE"), nullable=False), sa.Column("inspector_id", sa.Integer(), sa.ForeignKey("tenant_accounts.id", ondelete="SET NULL")), sa.Column("tag", sa.String(16), nullable=False), sa.Column("issue_types", postgresql.JSONB(), nullable=False, server_default="[]"), sa.Column("issue_description", sa.Text()), sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False))

def downgrade() -> None:
    op.drop_table("conversation_step_inspection_histories")
    op.drop_index("ix_step_inspections_tag", table_name="conversation_step_inspections")
    op.drop_index("ix_step_inspections_tenant_conversation", table_name="conversation_step_inspections")
    op.drop_table("conversation_step_inspections")
