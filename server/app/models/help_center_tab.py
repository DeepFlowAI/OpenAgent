"""
Help Center Tab ORM model.

A Tab inside a Help Center binds a knowledge base + a doc-meta filter set,
defining the visitor-visible document slice. Filters are stored as a JSONB
list of `{field, op, value}` items — the same shape used by tool fixed
filters elsewhere in the codebase, so the visitor side can later reuse the
existing filter pipeline.
"""
from sqlalchemy import (
    String,
    Integer,
    ForeignKey,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class HelpCenterTab(Base, TimestampMixin):
    __tablename__ = "help_center_tabs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    help_center_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("help_centers.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(32), nullable=False)
    # tab_slug is NULL only in the very rare race where the auto-generator
    # collides repeatedly; in practice the create endpoint always assigns one.
    tab_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fixed_filters: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "ix_help_center_tabs_help_center_id",
            "help_center_id",
            "sort_order",
            "id",
        ),
        # Partial unique index — tab_slug must be unique within a Help Center
        # only when set. Allows transient NULL during slug auto-allocation.
        Index(
            "uq_help_center_tabs_help_center_slug",
            "help_center_id",
            "tab_slug",
            unique=True,
            postgresql_where=text("tab_slug IS NOT NULL"),
        ),
    )
