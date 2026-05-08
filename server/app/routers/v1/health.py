"""
Health check router
"""
from fastapi import APIRouter

from app.configs.settings import settings
from app.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health status."""
    return HealthResponse(status="ok", version=settings.APP_VERSION)
