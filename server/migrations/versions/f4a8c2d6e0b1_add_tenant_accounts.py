"""add tenant accounts and resource access

Revision ID: f4a8c2d6e0b1
Revises: e9f0a1b2c3d4
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f4a8c2d6e0b1"
down_revision: str | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("username_normalized", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=False),
        sa.Column("email_normalized", sa.String(length=128), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            server_default="quality_inspector",
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column(
            "session_version", sa.Integer(), server_default="1", nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'quality_inspector')",
            name="ck_tenant_accounts_role",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_tenant_accounts_tenant_username_normalized",
        "tenant_accounts",
        ["tenant_id", "username_normalized"],
        unique=True,
    )
    op.create_index(
        "uq_tenant_accounts_tenant_email_normalized",
        "tenant_accounts",
        ["tenant_id", "email_normalized"],
        unique=True,
    )
    op.create_index(
        "ix_tenant_accounts_tenant_role",
        "tenant_accounts",
        ["tenant_id", "role"],
        unique=False,
    )

    op.create_table(
        "tenant_account_agents",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["tenant_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id", "agent_id"),
    )
    op.create_index(
        "ix_tenant_account_agents_agent_id",
        "tenant_account_agents",
        ["agent_id"],
        unique=False,
    )

    op.create_table(
        "tenant_account_knowledge_bases",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["tenant_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("account_id", "knowledge_base_id"),
    )
    op.create_index(
        "ix_tenant_account_knowledge_bases_knowledge_base_id",
        "tenant_account_knowledge_bases",
        ["knowledge_base_id"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO tenant_accounts (
                tenant_id,
                username,
                username_normalized,
                email,
                email_normalized,
                role,
                password_hash,
                session_version,
                created_at,
                updated_at
            )
            SELECT
                tenant_id,
                admin_username,
                lower(admin_username),
                COALESCE(
                    NULLIF(btrim(admin_email), ''),
                    'legacy-admin+' || md5(tenant_id) || '@example.invalid'
                ),
                lower(
                    COALESCE(
                        NULLIF(btrim(admin_email), ''),
                        'legacy-admin+' || md5(tenant_id) || '@example.invalid'
                    )
                ),
                'admin',
                admin_password_hash,
                1,
                created_at,
                updated_at
            FROM tenants
            ON CONFLICT (tenant_id, username_normalized) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_account_knowledge_bases_knowledge_base_id",
        table_name="tenant_account_knowledge_bases",
    )
    op.drop_table("tenant_account_knowledge_bases")
    op.drop_index(
        "ix_tenant_account_agents_agent_id",
        table_name="tenant_account_agents",
    )
    op.drop_table("tenant_account_agents")
    op.drop_index(
        "ix_tenant_accounts_tenant_role", table_name="tenant_accounts"
    )
    op.drop_index(
        "uq_tenant_accounts_tenant_email_normalized",
        table_name="tenant_accounts",
    )
    op.drop_index(
        "uq_tenant_accounts_tenant_username_normalized",
        table_name="tenant_accounts",
    )
    op.drop_table("tenant_accounts")
