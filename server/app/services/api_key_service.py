"""
API Key service — multi-key management with scopes.
"""
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.api_key_repository import ApiKeyRepository
from app.schemas.api_key import ApiKeyCreate

KEY_PREFIX = "sk-"
KEY_RANDOM_LENGTH = 48
MASK_DOTS = "••••••••••••"
VALID_SCOPES = {"chat", "config"}


def _generate_key() -> str:
    """Generate a random API key like sk-a1b2c3...48 hex chars."""
    return KEY_PREFIX + secrets.token_hex(KEY_RANDOM_LENGTH // 2)


def _mask_key(key_value: str) -> str:
    """Mask an API key for display: sk-abcd••••••••••••wxyz."""
    prefix = key_value[:7]
    suffix = key_value[-4:]
    return prefix + MASK_DOTS + suffix


def _validate_scopes(scopes: list[str]) -> str:
    """Validate and serialize scope list to comma-separated string."""
    if not scopes:
        raise ValidationError("At least one scope is required")
    invalid = set(scopes) - VALID_SCOPES
    if invalid:
        raise ValidationError(f"Invalid scopes: {', '.join(invalid)}. Valid: {', '.join(VALID_SCOPES)}")
    return ",".join(sorted(set(scopes)))


def _scopes_to_list(scopes_str: str) -> list[str]:
    """Convert comma-separated scopes string to list."""
    return [s.strip() for s in scopes_str.split(",") if s.strip()]


class ApiKeyService:

    # --- Legacy single-key compat ---

    @staticmethod
    async def get_or_create(db: AsyncSession, tenant_id: str):
        """Return existing key or auto-create one for the tenant (legacy)."""
        item = await ApiKeyRepository.get_by_tenant_id(db, tenant_id)
        if item:
            return item

        key_value = _generate_key()
        return await ApiKeyRepository.create(db, {
            "tenant_id": tenant_id,
            "name": "Default",
            "key_value": key_value,
            "masked_key": _mask_key(key_value),
            "scopes": "chat,config",
            "status": "active",
        })

    @staticmethod
    async def get_full_key(db: AsyncSession, tenant_id: str) -> str:
        """Return the full (unmasked) API key for clipboard copy (legacy)."""
        item = await ApiKeyRepository.get_by_tenant_id(db, tenant_id)
        if not item:
            item = await ApiKeyService.get_or_create(db, tenant_id)
        return item.key_value

    @staticmethod
    async def reset_key(db: AsyncSession, tenant_id: str):
        """Generate a new key, replacing the old one (legacy)."""
        item = await ApiKeyRepository.get_by_tenant_id(db, tenant_id)
        key_value = _generate_key()
        data = {
            "key_value": key_value,
            "masked_key": _mask_key(key_value),
        }
        if item:
            return await ApiKeyRepository.update(db, item, data)
        data.update({"tenant_id": tenant_id, "name": "Default", "scopes": "chat,config", "status": "active"})
        return await ApiKeyRepository.create(db, data)

    # --- Multi-key management ---

    @staticmethod
    async def list_keys(db: AsyncSession, tenant_id: str, page: int = 1, per_page: int = 20) -> dict:
        items, total = await ApiKeyRepository.list_by_tenant(db, tenant_id, page, per_page)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": [_enrich_item(item) for item in items],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def create_key(db: AsyncSession, tenant_id: str, data: ApiKeyCreate) -> dict:
        scopes_str = _validate_scopes(data.scopes)
        key_value = _generate_key()
        item = await ApiKeyRepository.create(db, {
            "tenant_id": tenant_id,
            "name": data.name,
            "description": data.description,
            "key_value": key_value,
            "masked_key": _mask_key(key_value),
            "scopes": scopes_str,
            "status": "active",
        })
        result = _enrich_item(item)
        result["key_value"] = key_value
        return result

    @staticmethod
    async def get_full_key_by_id(db: AsyncSession, tenant_id: str, key_id: int) -> str:
        """Return full key for clipboard copy (multi-key row)."""
        item = await ApiKeyRepository.get_by_id(db, key_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("API key not found")
        if item.status != "active":
            raise ValidationError("Cannot copy a revoked key")
        return item.key_value

    @staticmethod
    async def rotate_key(db: AsyncSession, tenant_id: str, key_id: int) -> dict:
        item = await ApiKeyRepository.get_by_id(db, key_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("API key not found")
        if item.status != "active":
            raise ValidationError("Cannot rotate a revoked key")

        new_key_value = _generate_key()
        item = await ApiKeyRepository.update(db, item, {
            "key_value": new_key_value,
            "masked_key": _mask_key(new_key_value),
        })
        result = _enrich_item(item)
        result["key_value"] = new_key_value
        return result

    @staticmethod
    async def revoke_key(db: AsyncSession, tenant_id: str, key_id: int) -> None:
        item = await ApiKeyRepository.get_by_id(db, key_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("API key not found")
        await ApiKeyRepository.delete(db, item)


def _enrich_item(item) -> dict:
    """Convert ORM item to dict with scopes as list."""
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "masked_key": item.masked_key,
        "scopes": _scopes_to_list(item.scopes),
        "status": item.status,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
