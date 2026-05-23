"""
Service hours router.
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_scope
from app.schemas.service_hours import (
    ServiceHoursCreate,
    ServiceHoursListResponse,
    ServiceHoursResponse,
    ServiceHoursUpdate,
)
from app.services.service_hours_service import ServiceHoursService

router = APIRouter(prefix="/service-hours", tags=["Service Hours"])


@router.get("", response_model=ServiceHoursListResponse)
async def list_service_hours(
    tenant_id: str = Depends(require_scope("config")),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List service hours configs for the current tenant."""
    return await ServiceHoursService.get_paginated(
        db, tenant_id, page=page, per_page=per_page
    )


@router.post(
    "",
    response_model=ServiceHoursResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_hours(
    body: ServiceHoursCreate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Create a service hours config."""
    return await ServiceHoursService.create(db, tenant_id, body)


@router.get("/{service_hours_id}", response_model=ServiceHoursResponse)
async def get_service_hours(
    service_hours_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Get service hours config by ID."""
    return await ServiceHoursService.get_for_tenant(
        db, tenant_id, service_hours_id
    )


@router.put("/{service_hours_id}", response_model=ServiceHoursResponse)
async def update_service_hours(
    service_hours_id: int,
    body: ServiceHoursUpdate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Update a service hours config."""
    return await ServiceHoursService.update(db, tenant_id, service_hours_id, body)


@router.delete("/{service_hours_id}", status_code=status.HTTP_200_OK)
async def delete_service_hours(
    service_hours_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a service hours config."""
    await ServiceHoursService.delete(db, tenant_id, service_hours_id)
    return {"message": "Deleted successfully"}
