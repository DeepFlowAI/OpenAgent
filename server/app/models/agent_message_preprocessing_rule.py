"""
Agent message preprocessing rule ORM model
"""
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class AgentMessagePreprocessingRule(Base, TimestampMixin):
    __tablename__ = "agent_message_preprocessing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    condition: Mapped[str] = mapped_column(String(1000), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    __table_args__ = (
        CheckConstraint(
            "action IN ('prefix', 'suffix')",
            name="ck_agent_msg_pre_rules_action",
        ),
        Index("ix_agent_msg_pre_rules_agent_id_id", "agent_id", "id"),
        Index("ix_agent_msg_pre_rules_tenant_id", "tenant_id"),
    )
