"""
Unit tests for authentication dependencies.
"""
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request

from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.db.deps import (
    AuthContext,
    resolve_auth,
    require_agent_access,
    require_admin_session_or_scope,
    require_api_key_scope,
    require_knowledge_base_access,
    require_user_session_or_scope,
)


def _bearer_request(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )


class TestResolveAuth:
    @pytest.mark.asyncio
    async def test_rejects_token_for_deleted_account(self):
        payload = {
            "sub": "7",
            "tenant_id": "T_TEST",
            "username": "deleted.user",
            "role": "admin",
            "account_version": 1,
        }

        with (
            patch(
                "app.core.security.decode_access_token",
                return_value=payload,
            ),
            patch(
                "app.repositories.account_repository.AccountRepository.get_by_id",
                AsyncMock(return_value=None),
            ),
        ):
            with pytest.raises(UnauthorizedError, match="Invalid token"):
                await resolve_auth(
                    _bearer_request("jwt-token"),
                    AsyncMock(),
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


class TestRequireAgentAccess:
    @pytest.mark.asyncio
    async def test_allows_authorized_quality_inspector(self):
        dependency = require_agent_access("chat")
        auth = AuthContext(
            tenant_id="T_TEST",
            role="quality_inspector",
            account_id=8,
        )

        with patch(
            "app.repositories.account_repository.AccountRepository.has_agent_access",
            AsyncMock(return_value=True),
        ), patch(
            "app.repositories.agent_repository.AgentRepository.get_by_id",
            AsyncMock(return_value=type("Agent", (), {"tenant_id": "T_TEST"})()),
        ):
            result = await dependency(3, auth, AsyncMock())

        assert result is auth

    @pytest.mark.asyncio
    async def test_rejects_unauthorized_quality_inspector(self):
        dependency = require_agent_access("chat")
        auth = AuthContext(
            tenant_id="T_TEST",
            role="quality_inspector",
            account_id=8,
        )

        with patch(
            "app.repositories.account_repository.AccountRepository.has_agent_access",
            AsyncMock(return_value=False),
        ), patch(
            "app.repositories.agent_repository.AgentRepository.get_by_id",
            AsyncMock(return_value=type("Agent", (), {"tenant_id": "T_TEST"})()),
        ):
            with pytest.raises(ForbiddenError, match="access"):
                await dependency(3, auth, AsyncMock())

    @pytest.mark.asyncio
    async def test_rejects_agent_from_another_tenant(self):
        dependency = require_agent_access("chat")
        auth = AuthContext(tenant_id="T_TEST", role="admin")

        with patch(
            "app.repositories.agent_repository.AgentRepository.get_by_id",
            AsyncMock(return_value=type("Agent", (), {"tenant_id": "T_OTHER"})()),
        ):
            with pytest.raises(NotFoundError, match="Agent not found"):
                await dependency(3, auth, AsyncMock())


class TestRequireKnowledgeBaseAccess:
    @pytest.mark.asyncio
    async def test_allows_authorized_quality_inspector(self):
        dependency = require_knowledge_base_access("chat")
        auth = AuthContext(
            tenant_id="T_TEST",
            role="quality_inspector",
            account_id=8,
        )

        with patch(
            "app.repositories.account_repository.AccountRepository.has_knowledge_base_access",
            AsyncMock(return_value=True),
        ), patch(
            "app.repositories.knowledge_base_repository.KnowledgeBaseRepository.get_by_id",
            AsyncMock(
                return_value=type(
                    "KnowledgeBase",
                    (),
                    {"tenant_id": "T_TEST", "status": "active"},
                )()
            ),
        ):
            result = await dependency(3, auth, AsyncMock())

        assert result is auth

    @pytest.mark.asyncio
    async def test_rejects_unauthorized_quality_inspector(self):
        dependency = require_knowledge_base_access("chat")
        auth = AuthContext(
            tenant_id="T_TEST",
            role="quality_inspector",
            account_id=8,
        )

        with patch(
            "app.repositories.account_repository.AccountRepository.has_knowledge_base_access",
            AsyncMock(return_value=False),
        ), patch(
            "app.repositories.knowledge_base_repository.KnowledgeBaseRepository.get_by_id",
            AsyncMock(
                return_value=type(
                    "KnowledgeBase",
                    (),
                    {"tenant_id": "T_TEST", "status": "active"},
                )()
            ),
        ):
            with pytest.raises(ForbiddenError, match="access"):
                await dependency(3, auth, AsyncMock())

    @pytest.mark.asyncio
    async def test_rejects_knowledge_base_from_another_tenant(self):
        dependency = require_knowledge_base_access("chat")
        auth = AuthContext(tenant_id="T_TEST", role="admin")

        with patch(
            "app.repositories.knowledge_base_repository.KnowledgeBaseRepository.get_by_id",
            AsyncMock(
                return_value=type(
                    "KnowledgeBase",
                    (),
                    {"tenant_id": "T_OTHER", "status": "active"},
                )()
            ),
        ):
            with pytest.raises(NotFoundError, match="Knowledge base not found"):
                await dependency(3, auth, AsyncMock())
