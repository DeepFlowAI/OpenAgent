"""
Document ORM model
"""
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    markdown_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    toc: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    slice_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_documents_kb_id", "knowledge_base_id"),
        Index("ix_documents_tenant_id", "tenant_id"),
        UniqueConstraint(
            "knowledge_base_id", "file_path", name="uq_documents_kb_filepath"
        ),
    )
