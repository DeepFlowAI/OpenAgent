"""
Unit tests for authentication dependencies.
"""
import pytest

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.db.deps import AuthContext, require_api_key_scope


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
