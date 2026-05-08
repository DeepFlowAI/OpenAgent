"""
API Key model — multiple keys per tenant with scopes for open API authentication.
"""
from sqlalchemy import String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_value: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    masked_key: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[str] = mapped_column(String(255), nullable=False, server_default="chat")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")

    __table_args__ = (
        Index("ix_api_keys_tenant_id", "tenant_id"),
    )
