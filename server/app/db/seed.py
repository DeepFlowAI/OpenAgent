"""System-level idempotent seed.

Runs once on app startup after Alembic migrations. Used to provision the
default single-tenant baseline for open-source deployments — when the
``tenants`` table is empty, create one tenant + admin so the app is usable
out of the box.

Every operation here MUST be idempotent — only fires when state is empty.
"""
import logging

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.models.tenant import Tenant, generate_tenant_id

logger = logging.getLogger(__name__)


async def seed_system_defaults(db: AsyncSession) -> None:
    """Seed system-level default data. Idempotent.

    Call site: ``app.main.lifespan`` after ``run_migrations()``.
    """
    await _ensure_default_tenant(db)


async def _ensure_default_tenant(db: AsyncSession) -> None:
    """Auto-provision a default tenant on first boot.

    Fires only when the ``tenants`` table is empty. This makes the open-source
    distribution usable out of the box (no separate tenant-provisioning step
    needed). Once any tenant exists — whether created here, by the closed-source
    Tenant API, or directly via SQL — this function becomes a no-op forever.
    """
    count = (await db.execute(select(func.count()).select_from(Tenant))).scalar_one()
    if count > 0:
        return

    password_hash = bcrypt.hashpw(
        settings.DEFAULT_ADMIN_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    # ``DEFAULT_TENANT_ID`` is also stored verbatim as the user-facing slug —
    # the model's ``generate_tenant_id`` would otherwise generate a random one.
    tenant = Tenant(
        tenant_id=settings.DEFAULT_TENANT_ID,
        name=settings.DEFAULT_TENANT_NAME,
        admin_username=settings.DEFAULT_ADMIN_USERNAME,
        admin_password_hash=password_hash,
    )
    db.add(tenant)
    await db.flush()

    logger.warning(
        "First-run init: created default tenant '%s' (id=%s) with admin '%s'. "
        "CHANGE THE PASSWORD ON FIRST LOGIN.",
        settings.DEFAULT_TENANT_ID,
        tenant.id,
        settings.DEFAULT_ADMIN_USERNAME,
    )
