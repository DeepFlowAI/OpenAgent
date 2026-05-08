"""Public system info — UX hints for the frontend.

This endpoint is intentionally **not** an authorisation gate. It tells the
frontend whether to render multi-tenant UI (login form's tenant field, tenant
admin pages, etc.). The actual authority over multi-tenant features comes
from whether the closed-source ``tenants`` extension is loaded — which
itself is controlled by file-system presence of the extension package, not
by any config flag.

OSS deployments never see closed-source extensions, so ``single_tenant_mode``
is always ``true`` for them.
"""
from fastapi import APIRouter, Request

from app.configs.settings import settings

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/info")
async def get_system_info(request: Request) -> dict:
    loaded = list(getattr(request.app.state, "loaded_extensions", []))
    has_tenants_ext = "tenants" in loaded
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "edition": "enterprise" if has_tenants_ext else "community",
        "single_tenant_mode": not has_tenants_ext,
        "default_tenant_id": settings.DEFAULT_TENANT_ID,
    }
