import random
import string
from datetime import datetime

from sqlalchemy import String, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin
from app.enums import TenantStatus


def generate_tenant_id() -> str:
    """Generate a unique tenant ID like T20260323A7F."""
    date_str = datetime.now().strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"T{date_str}{suffix}"


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, default=generate_tenant_id
    )
    slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TenantStatus.ENABLED.value
    )
    admin_username: Mapped[str] = mapped_column(String(64), nullable=False)
    admin_password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    admin_email: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_tenants_status", "status"),
        Index("uq_tenants_slug", "slug", unique=True),
    )
