"""
API Key router — system-level key management for the authenticated tenant.

Legacy single-key endpoints (GET/POST /system/api-key*) are preserved for backward compatibility.
New multi-key endpoints (GET/POST/DELETE /system/api-keys*) support multiple keys with scopes.
"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.deps import get_db
from app.schemas.api_key import (
    ApiKeyResponse,
    ApiKeyFullResponse,
    ApiKeyCreate,
    ApiKeyItemResponse,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
)
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/system", tags=["System"])


def _extract_tenant_id(request: Request) -> str:
    """Extract tenant_id from JWT in Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid authorization header")
    token = auth_header.split(" ", 1)[1]
    payload = decode_access_token(token)
    return str(payload["tenant_id"])


# ── Legacy single-key endpoints (backward compat) ──

@router.get("/api-key", response_model=ApiKeyResponse)
async def get_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get the masked API key for the current tenant (auto-creates if none)."""
    tenant_id = _extract_tenant_id(request)
    item = await ApiKeyService.get_or_create(db, tenant_id)
    return item


@router.get("/api-key/full", response_model=ApiKeyFullResponse)
async def get_full_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get the full API key for clipboard copy."""
    tenant_id = _extract_tenant_id(request)
    key_value = await ApiKeyService.get_full_key(db, tenant_id)
    return {"key_value": key_value}


@router.post("/api-key/reset", response_model=ApiKeyResponse)
async def reset_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Reset the API key, invalidating the old one."""
    tenant_id = _extract_tenant_id(request)
    item = await ApiKeyService.reset_key(db, tenant_id)
    return item


# ── Multi-key management endpoints ──

@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the current tenant."""
    tenant_id = _extract_tenant_id(request)
    return await ApiKeyService.list_keys(db, tenant_id, page=page, per_page=per_page)


@router.get("/api-keys/{key_id}/full", response_model=ApiKeyFullResponse)
async def get_api_key_full_by_id(
    request: Request,
    key_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get the full API key for clipboard copy (multi-key)."""
    tenant_id = _extract_tenant_id(request)
    key_value = await ApiKeyService.get_full_key_by_id(db, tenant_id, key_id)
    return {"key_value": key_value}


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: Request,
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. The full key is returned only once."""
    tenant_id = _extract_tenant_id(request)
    return await ApiKeyService.create_key(db, tenant_id, body)


@router.post("/api-keys/{key_id}/rotate", response_model=ApiKeyCreateResponse)
async def rotate_api_key(
    request: Request,
    key_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Rotate an API key — old value is immediately invalidated."""
    tenant_id = _extract_tenant_id(request)
    return await ApiKeyService.rotate_key(db, tenant_id, key_id)


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_200_OK)
async def revoke_api_key(
    request: Request,
    key_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Revoke (delete) an API key."""
    tenant_id = _extract_tenant_id(request)
    await ApiKeyService.revoke_key(db, tenant_id, key_id)
    return {"message": "API key revoked successfully"}
