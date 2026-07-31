"""Tenant account management routes."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import AuthContext, get_db, require_admin_session
from app.schemas.account import (
    AccountCreate,
    AccountDeleteResponse,
    AccountListResponse,
    AccountPageSize,
    AccountResourceOptionsResponse,
    AccountResponse,
    AccountUpdate,
)
from app.services.account_service import AccountService

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    q: str | None = Query(default=None, max_length=128),
    role: Literal["admin", "quality_inspector"] | None = None,
    page: int = Query(default=1, ge=1),
    per_page: AccountPageSize = AccountPageSize.DEFAULT,
    auth: AuthContext = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    """List accounts in the current tenant."""
    return await AccountService.get_paginated(
        db,
        auth.tenant_id,
        current_account_id=auth.account_id,
        q=q,
        role=role,
        page=page,
        per_page=int(per_page),
    )


@router.post(
    "", response_model=AccountResponse, status_code=status.HTTP_201_CREATED
)
async def create_account(
    body: AccountCreate,
    auth: AuthContext = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    """Create a tenant account."""
    return await AccountService.create(db, auth.tenant_id, body)


@router.get(
    "/resource-options", response_model=AccountResourceOptionsResponse
)
async def get_account_resource_options(
    auth: AuthContext = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    """List Agent and knowledge-base options for account grants."""
    return await AccountService.get_resource_options(db, auth.tenant_id)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    auth: AuthContext = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    """Get one account in the current tenant."""
    return await AccountService.get_by_id(
        db,
        auth.tenant_id,
        account_id,
        current_account_id=auth.account_id,
    )


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    body: AccountUpdate,
    auth: AuthContext = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    """Update account identity, role, password, and resource grants."""
    return await AccountService.update(
        db,
        auth.tenant_id,
        account_id,
        body,
        current_account_id=auth.account_id,
    )


@router.delete("/{account_id}", response_model=AccountDeleteResponse)
async def delete_account(
    account_id: int,
    auth: AuthContext = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    """Delete an account and its resource grants."""
    await AccountService.delete(
        db,
        auth.tenant_id,
        account_id,
        current_account_id=auth.account_id,
    )
    return {"message": "Account deleted"}
