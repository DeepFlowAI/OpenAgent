"""
Unit tests for authentication dependencies.
"""
import pytest
from starlette.requests import Request

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.db.deps import (
    AuthContext,
    require_admin_session_or_scope,
    require_api_key_scope,
    require_user_session_or_scope,
)


def _bearer_request(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )


class TestRequireApiKeyScope:

    @pytest.mark.asyncio
    async def test_allows_api_key_with_required_scope(self):
        dependency = require_api_key_scope("chat")

        tenant_id = await dependency(AuthContext(tenant_id="T_TEST", scopes=["chat"]))

        assert tenant_id == "T_TEST"

    @pytest.mark.asyncio
    async def test_rejects_jwt_or_legacy_auth_context(self):
        dependency = require_api_key_scope("chat")

        with pytest.raises(UnauthorizedError, match="Missing or invalid API key"):
            await dependency(AuthContext(tenant_id="T_TEST", scopes=None))

    @pytest.mark.asyncio
    async def test_rejects_api_key_without_required_scope(self):
        dependency = require_api_key_scope("chat")

        with pytest.raises(ForbiddenError, match="required scope"):
            await dependency(AuthContext(tenant_id="T_TEST", scopes=["config"]))


class TestRequireUserSessionOrScope:

    @pytest.mark.asyncio
    async def test_allows_member_jwt(self):
        dependency = require_user_session_or_scope("config")
        auth = AuthContext(tenant_id="T_TEST", scopes=None, role="member")

        result = await dependency(_bearer_request("jwt-token"), auth)

        assert result is auth

    @pytest.mark.asyncio
    async def test_allows_api_key_with_required_scope(self):
        dependency = require_user_session_or_scope("config")
        auth = AuthContext(tenant_id="T_TEST", scopes=["config"])

        result = await dependency(_bearer_request("sk-test"), auth)

        assert result is auth

    @pytest.mark.asyncio
    async def test_rejects_api_key_without_required_scope(self):
        dependency = require_user_session_or_scope("config")
        auth = AuthContext(tenant_id="T_TEST", scopes=["chat"])

        with pytest.raises(ForbiddenError, match="required scope: config"):
            await dependency(_bearer_request("sk-test"), auth)


class TestRequireAdminSessionOrScope:

    @pytest.mark.asyncio
    async def test_allows_admin_jwt(self):
        dependency = require_admin_session_or_scope("config")
        auth = AuthContext(tenant_id="T_TEST", scopes=None, role="admin")

        result = await dependency(_bearer_request("jwt-token"), auth)

        assert result is auth

    @pytest.mark.asyncio
    async def test_rejects_member_jwt(self):
        dependency = require_admin_session_or_scope("config")
        auth = AuthContext(tenant_id="T_TEST", scopes=None, role="member")

        with pytest.raises(ForbiddenError, match="management permission"):
            await dependency(_bearer_request("jwt-token"), auth)

    @pytest.mark.asyncio
    async def test_allows_api_key_with_required_scope(self):
        dependency = require_admin_session_or_scope("config")
        auth = AuthContext(tenant_id="T_TEST", scopes=["config"])

        result = await dependency(_bearer_request("sk-test"), auth)

        assert result is auth

    @pytest.mark.asyncio
    async def test_rejects_api_key_without_required_scope(self):
        dependency = require_admin_session_or_scope("config")
        auth = AuthContext(tenant_id="T_TEST", scopes=["chat"])

        with pytest.raises(ForbiddenError, match="required scope: config"):
            await dependency(_bearer_request("sk-test"), auth)
