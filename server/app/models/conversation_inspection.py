"""Human quality-inspection records for assistant conversation steps."""
from datetime import datetime
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base
from app.models.base import TimestampMixin


class ConversationStepInspection(Base, TimestampMixin):
    __tablename__ = "conversation_step_inspections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    step_id: Mapped[int] = mapped_column(ForeignKey("conversation_steps.id", ondelete="CASCADE"), nullable=False, unique=True)
    inspector_id: Mapped[int | None] = mapped_column(ForeignKey("tenant_accounts.id", ondelete="SET NULL"), nullable=True)
    tag: Mapped[str] = mapped_column(String(16), nullable=False)
    issue_types: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    issue_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_step_inspections_tenant_conversation", "tenant_id", "conversation_id"),
        Index("ix_step_inspections_tag", "tag"),
    )


class ConversationStepInspectionHistory(Base):
    __tablename__ = "conversation_step_inspection_histories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("conversation_step_inspections.id", ondelete="CASCADE"), nullable=False)
    inspector_id: Mapped[int | None] = mapped_column(ForeignKey("tenant_accounts.id", ondelete="SET NULL"), nullable=True)
    tag: Mapped[str] = mapped_column(String(16), nullable=False)
    issue_types: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    issue_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
