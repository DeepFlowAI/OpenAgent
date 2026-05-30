"""Public system info — UX hints for the frontend.

This endpoint is intentionally **not** an authorisation gate. It tells the
frontend whether to render multi-tenant login UI (tenant field on login /
forgot-password). Tenant CRUD is handled by an external Tenant Platform via
``X-API-Key``; this web app does not expose tenant admin pages.

OSS deployments never see closed-source extensions, so ``single_tenant_mode``
is always ``true`` for them.
"""
from fastapi import APIRouter, Request

from app.configs.settings import settings
from app.libs.llm.model_catalog import ui_models_as_dicts

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
        "llm_models": ui_models_as_dicts(settings.LLM_UI_MODELS),
    }
