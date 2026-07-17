"""Unit tests for attachment channel boundaries on chat routes."""

from types import SimpleNamespace

import pytest

from app.core.exceptions import ForbiddenError, ValidationError
from app.db.deps import AuthContext
from app.routers.v1 import chat as chat_router
from app.routers.v1 import public as public_router
from app.schemas.chat import ChatRequest


def _request() -> ChatRequest:
    return ChatRequest(
        attachments=[
            {
                "type": "file",
                "url": "https://files.example.com/contract.pdf",
                "name": "contract.pdf",
                "mime_type": "application/pdf",
                "size": 1024,
            }
        ]
    )


@pytest.mark.asyncio
async def test_authenticated_user_session_cannot_send_attachments():
    with pytest.raises(ForbiddenError, match="only supported with an API key"):
        await chat_router.chat(
            agent_id=3,
            body=_request(),
            request=SimpleNamespace(),
            auth=AuthContext(tenant_id="tenant-a", scopes=None, role="admin"),
            db=object(),
        )


@pytest.mark.asyncio
async def test_api_key_without_chat_scope_cannot_send_attachments():
    with pytest.raises(ForbiddenError, match="lacks required scope: chat"):
        await chat_router.chat(
            agent_id=3,
            body=_request(),
            request=SimpleNamespace(),
            auth=AuthContext(tenant_id="tenant-a", scopes=["config"]),
            db=object(),
        )


@pytest.mark.asyncio
async def test_public_channel_cannot_send_attachments(monkeypatch):
    async def fake_get_channel(db, token):
        return SimpleNamespace(agent_id=3)

    monkeypatch.setattr(
        public_router.ChannelService,
        "get_by_token",
        fake_get_channel,
    )

    with pytest.raises(ValidationError, match="not supported by public chat"):
        await public_router.public_chat(
            token="fake-channel-token",
            body=_request(),
            db=object(),
        )
