"""Tenant account and resource access ORM models."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class TenantAccount(Base, TimestampMixin):
    """A login account scoped to one tenant."""

    __tablename__ = "tenant_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str] = mapped_column(String(128), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="quality_inspector"
    )
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    session_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    __table_args__ = (
        Index(
            "uq_tenant_accounts_tenant_username_normalized",
            "tenant_id",
            "username_normalized",
            unique=True,
        ),
        Index(
            "uq_tenant_accounts_tenant_email_normalized",
            "tenant_id",
            "email_normalized",
            unique=True,
        ),
        Index("ix_tenant_accounts_tenant_role", "tenant_id", "role"),
        CheckConstraint(
            "role IN ('admin', 'quality_inspector')",
            name="ck_tenant_accounts_role",
        ),
    )


class TenantAccountAgent(Base):
    """Explicit Agent access for a quality inspector."""

    __tablename__ = "tenant_account_agents"

    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenant_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    agent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (Index("ix_tenant_account_agents_agent_id", "agent_id"),)


class TenantAccountKnowledgeBase(Base):
    """Explicit knowledge-base access for a quality inspector."""

    __tablename__ = "tenant_account_knowledge_bases"

    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenant_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        Index(
            "ix_tenant_account_knowledge_bases_knowledge_base_id",
            "knowledge_base_id",
        ),
    )
