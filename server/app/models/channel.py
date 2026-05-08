"""
Channel ORM model
"""
from sqlalchemy import String, Integer, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class Channel(Base, TimestampMixin):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    token: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    channel_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="web-sdk"
    )
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    access_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="url"
    )
    secret_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    __table_args__ = (
        Index("ix_channels_tenant_id", "tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_channels_tenant_name"),
    )
