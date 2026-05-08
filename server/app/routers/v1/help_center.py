"""
Help Center router (admin / system management).
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_scope
from app.schemas.help_center import (
    HelpCenterCreate,
    HelpCenterUpdate,
    HelpCenterResponse,
    HelpCenterListResponse,
    SlugAvailabilityResponse,
)
from app.services.help_center_service import HelpCenterService, serialize

router = APIRouter(prefix="/help-centers", tags=["Help Centers"])


@router.get("", response_model=HelpCenterListResponse)
async def list_help_centers(
    tenant_id: str = Depends(require_scope("config")),
    page: int = 1,
    per_page: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """List Help Centers for the current tenant, ordered by updated_at desc."""
    return await HelpCenterService.get_paginated(
        db, tenant_id, page=page, per_page=per_page
    )


@router.post(
    "",
    response_model=HelpCenterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_help_center(
    body: HelpCenterCreate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new Help Center. Public-access fields (slug / site_name /
    logo) are configured later via the detail page."""
    return await HelpCenterService.create(db, tenant_id, body)


@router.get("/check-slug", response_model=SlugAvailabilityResponse)
async def check_slug_availability(
    slug: str,
    exclude_id: int | None = None,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Real-time slug availability check for the detail page form. The PUT
    endpoint re-validates uniqueness, so this is purely UX sugar."""
    available = await HelpCenterService.is_slug_available(
        db, tenant_id, slug, exclude_id=exclude_id
    )
    return SlugAvailabilityResponse(available=available)


@router.get("/{help_center_id}", response_model=HelpCenterResponse)
async def get_help_center(
    help_center_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    item = await HelpCenterService.get_for_tenant(db, tenant_id, help_center_id)
    return serialize(item)


@router.put("/{help_center_id}", response_model=HelpCenterResponse)
async def update_help_center(
    help_center_id: int,
    body: HelpCenterUpdate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    return await HelpCenterService.update(db, tenant_id, help_center_id, body)


@router.delete("/{help_center_id}", status_code=status.HTTP_200_OK)
async def delete_help_center(
    help_center_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    await HelpCenterService.delete(db, tenant_id, help_center_id)
    return {"message": "Deleted successfully"}
