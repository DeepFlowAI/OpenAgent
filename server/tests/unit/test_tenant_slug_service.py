"""
Unit tests for tenant slug normalization, conflicts, and identifier resolution.
"""
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessError, ConflictError, ValidationError
from app.models.tenant import Tenant
from app.repositories.tenant_repository import TenantRepository
from app.schemas.tenant import TenantCreate, TenantUpdate
from app.services.tenant_service import TenantService


def _tenant(
    pk: int = 1,
    tenant_id: str = "T20260508ABC",
    slug: str | None = None,
    name: str = "Test Tenant",
) -> Tenant:
    return Tenant(
        id=pk,
        tenant_id=tenant_id,
        slug=slug,
        name=name,
        remark=None,
        status="enabled",
        admin_username="admin",
        admin_password_hash="hash",
    )


class TestTenantSlugService:

    @pytest.mark.asyncio
    async def test_create_normalizes_slug_before_persisting(self, monkeypatch):
        created = _tenant(slug="deepflow")
        create_mock = AsyncMock(return_value=created)
        monkeypatch.setattr(TenantRepository, "get_by_name", AsyncMock(return_value=None))
        monkeypatch.setattr(TenantRepository, "get_by_slug", AsyncMock(return_value=None))
        monkeypatch.setattr(
            TenantRepository, "get_by_tenant_id", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(TenantRepository, "create", create_mock)

        payload = TenantCreate(
            name="Test Tenant",
            slug="  DeepFlow  ",
            admin_username="admin",
            admin_password="password123",
        )

        result = await TenantService.create(AsyncMock(), payload)

        assert result["slug"] == "deepflow"
        assert create_mock.await_args.args[1]["slug"] == "deepflow"

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_slug_format(self, monkeypatch):
        monkeypatch.setattr(TenantRepository, "get_by_name", AsyncMock(return_value=None))

        payload = TenantCreate(
            name="Test Tenant",
            slug="/bad",
            admin_username="admin",
            admin_password="password123",
        )

        with pytest.raises(ValidationError, match="租户别名格式不正确"):
            await TenantService.create(AsyncMock(), payload)

    @pytest.mark.asyncio
    async def test_create_rejects_slug_matching_tenant_id(self, monkeypatch):
        monkeypatch.setattr(TenantRepository, "get_by_name", AsyncMock(return_value=None))
        monkeypatch.setattr(TenantRepository, "get_by_slug", AsyncMock(return_value=None))
        monkeypatch.setattr(
            TenantRepository,
            "get_by_tenant_id",
            AsyncMock(return_value=_tenant(tenant_id="deepflow")),
        )

        payload = TenantCreate(
            name="Test Tenant",
            slug="deepflow",
            admin_username="admin",
            admin_password="password123",
        )

        with pytest.raises(ConflictError, match="租户别名与系统租户 ID 冲突"):
            await TenantService.create(AsyncMock(), payload)

    @pytest.mark.asyncio
    async def test_update_empty_slug_clears_slug(self, monkeypatch):
        item = _tenant(slug="old-slug")
        update_mock = AsyncMock(return_value=_tenant(slug=None))
        monkeypatch.setattr(
            TenantRepository, "get_by_tenant_id", AsyncMock(return_value=item)
        )
        monkeypatch.setattr(TenantRepository, "update", update_mock)

        result = await TenantService.update(
            AsyncMock(), item.tenant_id, TenantUpdate(slug="")
        )

        assert result["slug"] is None
        assert update_mock.await_args.args[2]["slug"] is None

    @pytest.mark.asyncio
    async def test_resolve_identifier_uses_exact_id_and_lowercase_slug(
        self, monkeypatch
    ):
        tenant = _tenant(slug="deepflow")
        get_mock = AsyncMock(return_value=[tenant])
        monkeypatch.setattr(TenantRepository, "get_by_identifier", get_mock)

        result = await TenantService.resolve_identifier(AsyncMock(), "DeepFlow")

        assert result == tenant
        get_mock.assert_awaited_once()
        assert get_mock.await_args.args[1:] == ("DeepFlow", "deepflow")

    @pytest.mark.asyncio
    async def test_resolve_identifier_rejects_ambiguous_matches(self, monkeypatch):
        get_mock = AsyncMock(
            return_value=[
                _tenant(pk=1, tenant_id="deepflow"),
                _tenant(pk=2, tenant_id="T20260508XYZ", slug="deepflow"),
            ]
        )
        monkeypatch.setattr(TenantRepository, "get_by_identifier", get_mock)

        with pytest.raises(BusinessError, match="租户标识冲突，请联系管理员"):
            await TenantService.resolve_identifier(AsyncMock(), "deepflow")
