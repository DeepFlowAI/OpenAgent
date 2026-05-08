"""
Super admin model — platform-level administrator account.
"""
from sqlalchemy import String, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class SuperAdmin(Base, TimestampMixin):
    __tablename__ = "super_admins"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    __table_args__ = (
        Index("ix_super_admins_status", "status"),
    )
