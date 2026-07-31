"""Unit tests for tenant account business rules."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import BusinessError
from app.schemas.account import AccountCreate, AccountUpdate
from app.services.account_service import AccountService


def _account(**overrides):
    values = {
        "id": 10,
        "tenant_id": "T_TEST",
        "username": "quality.user",
        "email": "quality@example.com",
        "role": "quality_inspector",
        "password_hash": "hash",
        "session_version": 1,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestAccountService:
    @pytest.mark.asyncio
    async def test_create_maps_unique_error_raised_during_flush(self):
        db = AsyncMock()
        data = AccountCreate(
            username="admin.user",
            email="admin@example.com",
            role="admin",
            password="StrongPass1",
        )
        error = IntegrityError(
            "insert",
            {},
            RuntimeError(
                "uq_tenant_accounts_tenant_email_normalized"
            ),
        )

        with (
            patch.object(
                AccountService, "_password_hash", return_value="hash"
            ),
            patch(
                "app.services.account_service.AccountRepository.create",
                AsyncMock(side_effect=error),
            ),
        ):
            with pytest.raises(BusinessError) as exc_info:
                await AccountService.create(db, "T_TEST", data)

        assert exc_info.value.code == "ACCOUNT_EMAIL_EXISTS"
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_admin_discards_explicit_resource_grants(self):
        db = AsyncMock()
        item = _account(role="admin")
        data = AccountCreate(
            username="admin.user",
            email="admin@example.com",
            role="admin",
            password="StrongPass1",
            agent_ids=[1, 2],
            knowledge_base_ids=[3],
        )

        with (
            patch.object(
                AccountService, "_password_hash", return_value="hash"
            ),
            patch(
                "app.services.account_service.AccountRepository.create",
                AsyncMock(return_value=item),
            ),
            patch(
                "app.services.account_service.AccountRepository.replace_access",
                AsyncMock(),
            ) as replace_access,
            patch(
                "app.services.account_service.AccountRepository.count_admins",
                AsyncMock(return_value=1),
            ),
            patch(
                "app.services.account_service.AccountRepository.get_access_names",
                AsyncMock(return_value=({}, {})),
            ),
        ):
            result = await AccountService.create(db, "T_TEST", data)

        replace_access.assert_awaited_once_with(
            db,
            item.id,
            agent_ids=[],
            knowledge_base_ids=[],
        )
        assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_delete_current_account_is_rejected(self):
        db = AsyncMock()
        item = _account()

        with patch(
            "app.services.account_service.AccountRepository.get_by_id",
            AsyncMock(return_value=item),
        ):
            with pytest.raises(
                BusinessError, match="signed in"
            ) as exc_info:
                await AccountService.delete(
                    db,
                    "T_TEST",
                    item.id,
                    current_account_id=item.id,
                )

        assert exc_info.value.code == "CURRENT_ACCOUNT_RESTRICTED"

    @pytest.mark.asyncio
    async def test_delete_last_admin_is_rejected(self):
        db = AsyncMock()
        item = _account(role="admin")

        with (
            patch(
                "app.services.account_service.AccountRepository.get_by_id",
                AsyncMock(return_value=item),
            ),
            patch(
                "app.services.account_service.AccountRepository.lock_admins",
                AsyncMock(return_value=[item.id]),
            ),
            patch(
                "app.services.account_service.AccountRepository.count_admins",
                AsyncMock(return_value=1),
            ),
        ):
            with pytest.raises(
                BusinessError, match="administrator"
            ) as exc_info:
                await AccountService.delete(
                    db,
                    "T_TEST",
                    item.id,
                    current_account_id=999,
                )

        assert exc_info.value.code == "LAST_ADMIN_REQUIRED"

    @pytest.mark.asyncio
    async def test_resource_only_update_keeps_session_version(self):
        db = AsyncMock()
        item = _account()
        data = AccountUpdate(
            username=item.username,
            email=item.email,
            role="quality_inspector",
            agent_ids=[1],
            knowledge_base_ids=[2],
        )

        with (
            patch(
                "app.services.account_service.AccountRepository.get_by_id",
                AsyncMock(return_value=item),
            ),
            patch(
                "app.services.account_service.AccountRepository.validate_agent_ids",
                AsyncMock(return_value=True),
            ),
            patch(
                "app.services.account_service.AccountRepository.validate_knowledge_base_ids",
                AsyncMock(return_value=True),
            ),
            patch(
                "app.services.account_service.AccountRepository.update",
                AsyncMock(return_value=item),
            ) as update,
            patch(
                "app.services.account_service.AccountRepository.replace_access",
                AsyncMock(),
            ),
            patch(
                "app.services.account_service.AccountRepository.count_admins",
                AsyncMock(return_value=1),
            ),
            patch(
                "app.services.account_service.AccountRepository.get_access_names",
                AsyncMock(return_value=({item.id: [(1, "Agent")]}, {})),
            ),
        ):
            await AccountService.update(
                db,
                "T_TEST",
                item.id,
                data,
                current_account_id=999,
            )

        update_data = update.await_args.args[2]
        assert "session_version" not in update_data

    @pytest.mark.asyncio
    async def test_password_update_increments_session_version(self):
        db = AsyncMock()
        item = _account()
        data = AccountUpdate(
            username=item.username,
            email=item.email,
            role="quality_inspector",
            password="NewStrong1",
        )

        with (
            patch.object(
                AccountService, "_password_hash", return_value="new-hash"
            ),
            patch(
                "app.services.account_service.AccountRepository.get_by_id",
                AsyncMock(return_value=item),
            ),
            patch(
                "app.services.account_service.AccountRepository.update",
                AsyncMock(return_value=item),
            ) as update,
            patch(
                "app.services.account_service.AccountRepository.replace_access",
                AsyncMock(),
            ),
            patch(
                "app.services.account_service.AccountRepository.count_admins",
                AsyncMock(return_value=1),
            ),
            patch(
                "app.services.account_service.AccountRepository.get_access_names",
                AsyncMock(return_value=({}, {})),
            ),
        ):
            await AccountService.update(
                db,
                "T_TEST",
                item.id,
                data,
                current_account_id=999,
            )

        assert update.await_args.args[2]["session_version"] == 2
