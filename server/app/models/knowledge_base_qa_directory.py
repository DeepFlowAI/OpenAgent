"""Knowledge-base QA directory ORM model."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class KnowledgeBaseQaDirectory(Base, TimestampMixin):
    __tablename__ = "knowledge_base_qa_directories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("knowledge_base_qa_directories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        Index(
            "ix_kb_qa_dirs_tenant_kb_parent_sort",
            "tenant_id",
            "knowledge_base_id",
            "parent_id",
            "sort_order",
        ),
        Index(
            "uq_kb_qa_dirs_root_name",
            "knowledge_base_id",
            "name",
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
        ),
        UniqueConstraint(
            "knowledge_base_id",
            "parent_id",
            "name",
            name="uq_kb_qa_dirs_parent_name",
        ),
        CheckConstraint("sort_order >= 0", name="ck_kb_qa_dirs_sort_order"),
    )
