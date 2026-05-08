"""
Slice ORM model
"""
from sqlalchemy import String, Text, Integer, Index, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False

from app.db.session import Base
from app.models.base import TimestampMixin

EMBEDDING_DIMENSION = 1024


class Slice(Base, TimestampMixin):
    __tablename__ = "slices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_for_search: Mapped[str | None] = mapped_column(Text, nullable=True)
    toc_path: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    toc_ancestors: Mapped[str | None] = mapped_column(Text, nullable=True)
    slice_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    doc_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    markdown_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    slice_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    if HAS_PGVECTOR:
        embedding = Column(Vector(EMBEDDING_DIMENSION), nullable=True)
    else:
        embedding = Column("embedding", nullable=True)

    __table_args__ = (
        Index("ix_slices_document_id", "document_id"),
        Index("ix_slices_kb_id", "knowledge_base_id"),
        Index("ix_slices_tenant_id", "tenant_id"),
    )
