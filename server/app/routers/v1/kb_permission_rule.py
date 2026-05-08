"""
KbPermissionRule router
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db
from app.schemas.kb_permission_rule import (
    KbPermissionRuleCreate,
    KbPermissionRuleUpdate,
    KbPermissionRuleResponse,
)
from app.services.kb_permission_rule_service import KbPermissionRuleService

router = APIRouter(
    prefix="/knowledge-bases/{kb_id}/permission-rules",
    tags=["KbPermissionRules"],
)


@router.get("", response_model=list[KbPermissionRuleResponse])
async def list_permission_rules(
    kb_id: int,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all permission rules for a knowledge base"""
    return await KbPermissionRuleService.list_rules(db, tenant_id, kb_id)


@router.post(
    "", response_model=KbPermissionRuleResponse, status_code=status.HTTP_201_CREATED
)
async def create_permission_rule(
    kb_id: int,
    body: KbPermissionRuleCreate,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Create a new permission rule"""
    return await KbPermissionRuleService.create(db, tenant_id, kb_id, body)


@router.get("/{rule_id}", response_model=KbPermissionRuleResponse)
async def get_permission_rule(
    kb_id: int,
    rule_id: int,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a permission rule by ID"""
    return await KbPermissionRuleService.get_by_id(db, tenant_id, kb_id, rule_id)


@router.put("/{rule_id}", response_model=KbPermissionRuleResponse)
async def update_permission_rule(
    kb_id: int,
    rule_id: int,
    body: KbPermissionRuleUpdate,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Update a permission rule"""
    return await KbPermissionRuleService.update(db, tenant_id, kb_id, rule_id, body)


@router.delete("/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_permission_rule(
    kb_id: int,
    rule_id: int,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a permission rule"""
    await KbPermissionRuleService.delete(db, tenant_id, kb_id, rule_id)
    return {"message": "Deleted successfully"}


@router.patch("/{rule_id}/toggle", response_model=KbPermissionRuleResponse)
async def toggle_permission_rule(
    kb_id: int,
    rule_id: int,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Toggle enabled/disabled status of a permission rule"""
    return await KbPermissionRuleService.toggle(db, tenant_id, kb_id, rule_id)
