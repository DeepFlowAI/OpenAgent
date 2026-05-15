"""
KnowledgeBase ORM model
"""
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    git_url: Mapped[str] = mapped_column(String(512), nullable=False)
    git_branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    auth_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    nav_config: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_knowledge_bases_tenant_id", "tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_knowledge_bases_tenant_name"),
    )
