"""
KbPermissionRule ORM model
"""
from sqlalchemy import String, Integer, Boolean, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class KbPermissionRule(Base, TimestampMixin):
    __tablename__ = "kb_permission_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    user_conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    scope_operator: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_labels: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_kb_perm_rules_tenant_kb", "tenant_id", "knowledge_base_id"),
    )
