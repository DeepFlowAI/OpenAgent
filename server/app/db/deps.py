from collections.abc import AsyncGenerator
from dataclasses import dataclass

import redis.asyncio as aioredis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import redis_client
from app.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_redis() -> aioredis.Redis:
    return redis_client.client


# ── Auth context ──

@dataclass
class AuthContext:
    """Resolved authentication context."""
    tenant_id: str
    scopes: list[str] | None = None  # None = full access (JWT / legacy query)


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
            return AuthContext(tenant_id=str(payload["tenant_id"]), scopes=None)
        except Exception:
            raise UnauthorizedError("Invalid token")

    tenant_id = request.query_params.get("tenant_id")
    if tenant_id:
        return AuthContext(tenant_id=tenant_id, scopes=None)

    raise UnauthorizedError("Missing authentication")


def require_scope(scope: str):
    """Dependency factory — resolves auth and checks the required scope.

    Returns tenant_id string so it's a drop-in replacement for the old
    `tenant_id: str` query parameter.
    """
    async def _check(auth: AuthContext = Depends(resolve_auth)) -> str:
        from app.core.exceptions import ForbiddenError
        if auth.scopes is not None and scope not in auth.scopes:
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
