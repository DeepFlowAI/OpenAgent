"""Unit tests for tenant account login behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bcrypt
import pytest

from app.core.exceptions import UnauthorizedError
from app.schemas.auth import LoginRequest, ResetPasswordRequest
from app.services.auth_service import AuthService


def _tenant():
    return SimpleNamespace(
        id=1,
        tenant_id="T_TEST",
        status="enabled",
        admin_username="legacy-admin",
        admin_email="legacy@example.com",
        admin_password_hash="unused",
    )


def _account():
    password_hash = bcrypt.hashpw(
        b"StrongPass1", bcrypt.gensalt()
    ).decode("utf-8")
    return SimpleNamespace(
        id=7,
        username="quality.user",
        email="quality@example.com",
        role="quality_inspector",
        password_hash=password_hash,
        session_version=3,
    )


class TestAccountAuth:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "identifier", ["quality.user", "QUALITY.USER", "quality@example.com"]
    )
    async def test_login_accepts_username_or_email_case_insensitively(
        self, identifier: str
    ):
        db = AsyncMock()
        tenant = _tenant()
        account = _account()

        with (
            patch(
                "app.services.auth_service.TenantService.resolve_identifier",
                AsyncMock(return_value=tenant),
            ),
            patch(
                "app.services.auth_service.AccountRepository.get_by_identifier",
                AsyncMock(return_value=account),
            ),
        ):
            result = await AuthService.login(
                db,
                LoginRequest(
                    tenant="T_TEST",
                    username=identifier,
                    password="StrongPass1",
                ),
            )

        assert result["user"]["id"] == account.id
        assert result["user"]["role"] == "quality_inspector"
        assert result["user"]["email"] == account.email

    @pytest.mark.asyncio
    async def test_wrong_password_uses_unified_error(self):
        db = AsyncMock()

        with (
            patch(
                "app.services.auth_service.TenantService.resolve_identifier",
                AsyncMock(return_value=_tenant()),
            ),
            patch(
                "app.services.auth_service.AccountRepository.get_by_identifier",
                AsyncMock(return_value=_account()),
            ),
        ):
            with pytest.raises(
                UnauthorizedError,
                match="Invalid tenant, account or password",
            ):
                await AuthService.login(
                    db,
                    LoginRequest(
                        tenant="T_TEST",
                        username="quality.user",
                        password="WrongPass1",
                    ),
                )

    @pytest.mark.asyncio
    async def test_reset_password_invalidates_existing_sessions(self):
        db = AsyncMock()
        account = _account()
        code_record = SimpleNamespace(used=False)

        with (
            patch(
                "app.services.auth_service.TenantService.resolve_identifier",
                AsyncMock(return_value=_tenant()),
            ),
            patch(
                "app.services.auth_service.AccountRepository.get_by_identifier",
                AsyncMock(return_value=account),
            ),
            patch(
                "app.services.auth_service.AccountRepository.count_accounts",
                AsyncMock(return_value=1),
            ),
            patch(
                "app.services.auth_service.PasswordResetRepository.find_valid_code",
                AsyncMock(return_value=code_record),
            ),
            patch(
                "app.services.auth_service.PasswordResetRepository.mark_used",
                AsyncMock(),
            ),
            patch(
                "app.services.auth_service.AccountRepository.update",
                AsyncMock(return_value=account),
            ) as update,
            patch(
                "app.services.auth_service.bcrypt.hashpw",
                return_value=b"new-hash",
            ),
        ):
            await AuthService.reset_password(
                db,
                ResetPasswordRequest(
                    tenant="T_TEST",
                    username=account.email,
                    verify_code="123456",
                    new_password="NewStrong1",
                ),
            )

        assert update.await_args.args[2]["session_version"] == 4
        db.commit.assert_awaited_once()
