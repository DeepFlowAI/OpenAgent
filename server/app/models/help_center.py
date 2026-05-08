"""
Help Center ORM model.

Represents one Help Center instance owned by a tenant. The instance can be
published on the platform's default docs host as `/hc/{public_slug}/...`.

Public-access fields (`public_slug`, `site_name`, `publisher_logo_url`) are
nullable so a Help Center can exist before the user has configured visitor
access.

Slug uniqueness is GLOBAL (not per-tenant): the visitor URL
`https://{PUBLIC_DOCS_HOST}/hc/{public_slug}/...` lives on a single shared
host, so two tenants cannot pick the same slug without the public path
becoming ambiguous. Enforced by a partial unique index defined alongside the
model so Alembic autogenerate keeps it in sync.
"""
from sqlalchemy import String, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class HelpCenter(Base, TimestampMixin):
    __tablename__ = "help_centers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Public-access configuration. All three are NULL until the user finalizes
    # the "Public access" section in the detail page.
    public_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    site_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publisher_logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    __table_args__ = (
        Index("ix_help_centers_tenant_id", "tenant_id"),
        # Global partial unique index — at most one Help Center may publish
        # under any given public_slug, so the visitor path
        # /hc/{public_slug}/... resolves to a single tenant. Unpublished rows
        # (public_slug IS NULL) are exempt so multiple Help Centers may
        # coexist before any of them claims a slug.
        Index(
            "uq_help_centers_public_slug",
            "public_slug",
            unique=True,
            postgresql_where=text("public_slug IS NOT NULL"),
        ),
    )
