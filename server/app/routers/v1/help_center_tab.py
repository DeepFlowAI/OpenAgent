"""
Help Center Tab router (admin / system management).

Routes are nested under /help-centers/{help_center_id}/tabs to make tenant
isolation and Help Center ownership checks unambiguous at the path level.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_scope
from app.schemas.help_center_tab import (
    HelpCenterTabCreate,
    HelpCenterTabUpdate,
    HelpCenterTabResponse,
    HelpCenterTabListResponse,
    TabReorderRequest,
    TabSlugAvailabilityResponse,
)
from app.services.help_center_tab_service import HelpCenterTabService


router = APIRouter(
    prefix="/help-centers/{help_center_id}/tabs",
    tags=["Help Center Tabs"],
)


@router.get("", response_model=HelpCenterTabListResponse)
async def list_tabs(
    help_center_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    return await HelpCenterTabService.list_for_help_center(
        db, tenant_id, help_center_id
    )


@router.post(
    "",
    response_model=HelpCenterTabResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tab(
    help_center_id: int,
    body: HelpCenterTabCreate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    return await HelpCenterTabService.create(
        db, tenant_id, help_center_id, body
    )


@router.post("/reorder", response_model=HelpCenterTabListResponse)
async def reorder_tabs(
    help_center_id: int,
    body: TabReorderRequest,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    return await HelpCenterTabService.reorder(
        db, tenant_id, help_center_id, body.tab_ids
    )


@router.get("/check-slug", response_model=TabSlugAvailabilityResponse)
async def check_tab_slug(
    help_center_id: int,
    slug: str,
    exclude_id: int | None = None,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    available = await HelpCenterTabService.is_slug_available(
        db, tenant_id, help_center_id, slug, exclude_id=exclude_id
    )
    return TabSlugAvailabilityResponse(available=available)


@router.put("/{tab_id}", response_model=HelpCenterTabResponse)
async def update_tab(
    help_center_id: int,
    tab_id: int,
    body: HelpCenterTabUpdate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    return await HelpCenterTabService.update(
        db, tenant_id, help_center_id, tab_id, body
    )


@router.delete("/{tab_id}", status_code=status.HTTP_200_OK)
async def delete_tab(
    help_center_id: int,
    tab_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    await HelpCenterTabService.delete(
        db, tenant_id, help_center_id, tab_id
    )
    return {"message": "Deleted successfully"}
