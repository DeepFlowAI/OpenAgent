"""Knowledge-base QA ORM model."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class KnowledgeBaseQa(Base, TimestampMixin):
    __tablename__ = "knowledge_base_qas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    directory_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("knowledge_base_qa_directories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    access_keywords: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    process_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="processing", server_default="processing"
    )
    process_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    process_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    __table_args__ = (
        Index(
            "ix_kb_qas_tenant_kb_updated",
            "tenant_id",
            "knowledge_base_id",
            "updated_at",
        ),
        Index(
            "ix_kb_qas_kb_directory",
            "knowledge_base_id",
            "directory_id",
        ),
        UniqueConstraint(
            "knowledge_base_id", "question", name="uq_kb_qas_kb_question"
        ),
        UniqueConstraint("document_id", name="uq_kb_qas_document_id"),
        CheckConstraint(
            "process_status IN ('processing', 'ready', 'failed')",
            name="ck_kb_qas_process_status",
        ),
    )
