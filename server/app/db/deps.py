from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass

import redis.asyncio as aioredis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import redis_client
from app.db.session import session_scope


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with session_scope() as session:
        yield session


async def get_redis() -> aioredis.Redis:
    return redis_client.client


# ── Auth context ──

@dataclass
class AuthContext:
    """Resolved authentication context."""
    tenant_id: str
    scopes: list[str] | None = None  # None = full access (JWT / legacy query)
    role: str | None = None
    account_id: int | None = None
    username: str | None = None
    email: str | None = None


async def resolve_auth(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Resolve tenant identity from Bearer API key, JWT, or legacy query param.

    Priority: Bearer sk-... (API key) > Bearer JWT > Query param tenant_id.
    """
    from app.core.exceptions import UnauthorizedError
    from app.core.security import decode_access_token
    from app.repositories.api_key_repository import ApiKeyRepository

    auth_header = request.headers.get("Authorization")

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]

        if token.startswith("sk-"):
            api_key = await ApiKeyRepository.get_by_key_value(db, token)
            if not api_key:
                raise UnauthorizedError("Invalid API key")
            if api_key.status != "active":
                raise UnauthorizedError("API key has been revoked")
            scopes = [s.strip() for s in api_key.scopes.split(",") if s.strip()]
            return AuthContext(tenant_id=api_key.tenant_id, scopes=scopes)

        try:
            payload = decode_access_token(token)
            auth = AuthContext(
                tenant_id=str(payload["tenant_id"]),
                scopes=None,
                role=str(payload.get("role") or ""),
                account_id=(
                    int(payload["sub"])
                    if payload.get("account_version") is not None
                    else None
                ),
                username=str(payload.get("username") or ""),
                email=payload.get("email"),
            )
            from app.repositories.account_repository import AccountRepository

            account = None
            if auth.account_id is not None:
                account = await AccountRepository.get_by_id(
                    db, auth.tenant_id, auth.account_id
                )
            elif auth.username:
                account = await AccountRepository.get_by_identifier(
                    db, auth.tenant_id, auth.username
                )
            if account:
                token_version = payload.get("account_version")
                if (
                    token_version is not None
                    and int(token_version) != account.session_version
                ):
                    raise UnauthorizedError("Session is no longer valid")
                auth.account_id = account.id
                auth.username = account.username
                auth.email = account.email
                auth.role = account.role
            elif (
                payload.get("account_version") is not None
                or await AccountRepository.count_accounts(
                    db, auth.tenant_id
                )
                > 0
            ):
                raise UnauthorizedError("Account no longer exists")
            return auth
        except Exception:
            raise UnauthorizedError("Invalid token")

    tenant_id = request.query_params.get("tenant_id")
    if tenant_id:
        return AuthContext(tenant_id=tenant_id, scopes=None)

    raise UnauthorizedError("Missing authentication")


async def require_user_session(
    request: Request,
    auth: AuthContext = Depends(resolve_auth),
) -> AuthContext:
    """Require an authenticated user JWT instead of an API key or query fallback."""
    from app.core.exceptions import ForbiddenError

    authorization = request.headers.get("Authorization", "")
    if (
        not authorization.startswith("Bearer ")
        or authorization.removeprefix("Bearer ").startswith("sk-")
        or auth.scopes is not None
        or not auth.role
    ):
        raise ForbiddenError("This operation requires an authenticated user session")
    return auth


async def require_admin_session(
    auth: AuthContext = Depends(require_user_session),
) -> AuthContext:
    """Require a tenant administrator user session."""
    from app.core.exceptions import ForbiddenError

    if auth.role != "admin":
        raise ForbiddenError(
            "This operation requires administrator management permission"
        )
    return auth


def require_scope(scope: str):
    """Dependency factory — resolves auth and checks the required scope.

    Returns tenant_id string so it's a drop-in replacement for the old
    `tenant_id: str` query parameter.
    """
    async def _check(auth: AuthContext = Depends(resolve_auth)) -> str:
        from app.core.exceptions import ForbiddenError
        if auth.scopes is not None and scope not in auth.scopes:
            raise ForbiddenError(f"API key lacks required scope: {scope}")
        if auth.scopes is None and auth.role == "quality_inspector" and scope == "config":
            raise ForbiddenError("This operation requires administrator permission")
        return auth.tenant_id
    return _check


def require_user_session_or_scope(
    scope: str,
) -> Callable[..., Awaitable[AuthContext]]:
    """Allow an authenticated user session or an API key with ``scope``."""

    async def _check(
        request: Request,
        auth: AuthContext = Depends(resolve_auth),
    ) -> AuthContext:
        if auth.scopes is not None:
            from app.core.exceptions import ForbiddenError

            if scope not in auth.scopes:
                raise ForbiddenError(f"API key lacks required scope: {scope}")
            return auth
        return await require_user_session(request, auth)

    return _check


def require_agent_access(
    scope: str,
) -> Callable[..., Awaitable[AuthContext]]:
    """Require scope or access to the Agent selected by the route."""

    async def _check(
        agent_id: int,
        auth: AuthContext = Depends(resolve_auth),
        db: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        from app.core.exceptions import ForbiddenError, NotFoundError
        from app.repositories.account_repository import AccountRepository
        from app.repositories.agent_repository import AgentRepository

        if auth.scopes is not None:
            if scope not in auth.scopes:
                raise ForbiddenError(f"API key lacks required scope: {scope}")
        agent = await AgentRepository.get_by_id(db, agent_id)
        if not agent or agent.tenant_id != auth.tenant_id:
            raise NotFoundError("Agent not found")
        if auth.role == "quality_inspector":
            if auth.account_id is None or not await AccountRepository.has_agent_access(
                db, auth.account_id, agent_id
            ):
                raise ForbiddenError("You do not have access to this Agent")
        return auth

    return _check


def require_knowledge_base_access(
    scope: str,
) -> Callable[..., Awaitable[AuthContext]]:
    """Require scope or access to the knowledge base selected by the route."""

    async def _check(
        kb_id: int,
        auth: AuthContext = Depends(resolve_auth),
        db: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        from app.core.exceptions import ForbiddenError, NotFoundError
        from app.repositories.account_repository import AccountRepository
        from app.repositories.knowledge_base_repository import (
            KnowledgeBaseRepository,
        )

        if auth.scopes is not None:
            if scope not in auth.scopes:
                raise ForbiddenError(f"API key lacks required scope: {scope}")
        knowledge_base = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if (
            not knowledge_base
            or knowledge_base.status == "deleted"
            or knowledge_base.tenant_id != auth.tenant_id
        ):
            raise NotFoundError("Knowledge base not found")
        if auth.role == "quality_inspector":
            if (
                auth.account_id is None
                or not await AccountRepository.has_knowledge_base_access(
                    db, auth.account_id, kb_id
                )
            ):
                raise ForbiddenError(
                    "You do not have access to this knowledge base"
                )
        return auth

    return _check


def require_admin_session_or_scope(
    scope: str,
) -> Callable[..., Awaitable[AuthContext]]:
    """Allow an administrator session or an API key with ``scope``."""

    async def _check(
        request: Request,
        auth: AuthContext = Depends(resolve_auth),
    ) -> AuthContext:
        if auth.scopes is not None:
            from app.core.exceptions import ForbiddenError

            if scope not in auth.scopes:
                raise ForbiddenError(f"API key lacks required scope: {scope}")
            return auth
        user_auth = await require_user_session(request, auth)
        return await require_admin_session(user_auth)

    return _check


def require_api_key_scope(scope: str):
    """Dependency factory for OpenAPI routes that must use a scoped API key."""
    async def _check(auth: AuthContext = Depends(resolve_auth)) -> str:
        from app.core.exceptions import ForbiddenError, UnauthorizedError
        if auth.scopes is None:
            raise UnauthorizedError("Missing or invalid API key")
        if scope not in auth.scopes:
            raise ForbiddenError(f"API key lacks required scope: {scope}")
        return auth.tenant_id
    return _check


# ── Legacy verify_api_key (kept for backward compat with search / document routes) ──

async def verify_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> str:
    """Validate Bearer API key and return the owning tenant_id.

    Deprecated — prefer require_scope() for new routes.
    """
    from app.core.exceptions import UnauthorizedError
    from app.repositories.api_key_repository import ApiKeyRepository

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header")

    key_value = auth_header.split(" ", 1)[1]
    if not key_value.startswith("sk-"):
        raise UnauthorizedError("Invalid API key format")

    api_key = await ApiKeyRepository.get_by_key_value(db, key_value)
    if not api_key:
        raise UnauthorizedError("Invalid API key")
    if api_key.status != "active":
        raise UnauthorizedError("API key has been revoked")

    return api_key.tenant_id
