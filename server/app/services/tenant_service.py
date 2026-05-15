"""
Core tenant service — methods required by auth and other open-source modules.

The closed-source tenants extension (private/extensions/server/tenants/)
adds CRUD operations for the tenant-platform API on top of this.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models.tenant import Tenant
from app.repositories.tenant_repository import TenantRepository


class TenantService:

    @staticmethod
    async def resolve_identifier(db: AsyncSession, identifier: str) -> Tenant | None:
        raw_identifier = identifier.strip()
        slug_identifier = raw_identifier.lower()
        matches = await TenantRepository.get_by_identifier(
            db, raw_identifier, slug_identifier
        )
        unique_matches = {tenant.id: tenant for tenant in matches}
        if len(unique_matches) > 1:
            raise BusinessError("租户标识冲突，请联系管理员")
        if not unique_matches:
            return None
        return next(iter(unique_matches.values()))
