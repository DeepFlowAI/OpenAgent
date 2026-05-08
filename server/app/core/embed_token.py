"""
Embed Token — JWT-based short-lived token for Web SDK / URL mode.

The token is signed with a channel's secret_key (HMAC-SHA256) and carries
the §4 unified customer context in its payload.
"""
import time

import jwt

from app.core.exceptions import UnauthorizedError

ALGORITHM = "HS256"
DEFAULT_TTL_SECONDS = 86400  # 24 hours


def sign_embed_token(
    secret_key: str,
    *,
    channel_id: int,
    tenant_id: str,
    external_user_id: str | None = None,
    display_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    avatar_url: str | None = None,
    source: str = "embed",
    title: str | None = None,
    metadata: dict | None = None,
    ttl: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Sign an embed token containing customer context."""
    now = int(time.time())
    payload: dict = {
        "channel_id": channel_id,
        "tenant_id": tenant_id,
        "source": source,
        "iat": now,
        "exp": now + ttl,
    }
    # Optional customer context fields
    if external_user_id is not None:
        payload["external_user_id"] = external_user_id
    if display_name is not None:
        payload["display_name"] = display_name
    if email is not None:
        payload["email"] = email
    if phone is not None:
        payload["phone"] = phone
    if avatar_url is not None:
        payload["avatar_url"] = avatar_url
    if title is not None:
        payload["title"] = title
    if metadata:
        payload["metadata"] = metadata

    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def verify_embed_token(secret_key: str, token: str) -> dict:
    """Verify and decode an embed token.

    Returns the decoded payload dict.
    Raises UnauthorizedError on invalid or expired tokens.
    """
    try:
        return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Embed token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid embed token")
