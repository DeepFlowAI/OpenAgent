"""
Integration tests for the public channel routes (no-auth SDK / chat-page surface).

The most security-relevant guard here is the conversation-ownership check on
``GET /v1/public/channels/{token}/conversations/{conversation_id}/steps`` —
without it any browser-visible channel token could enumerate conversations
across tenants. We assert the 404 path and a positive control on the same
channel for symmetry.
"""
import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.services.detached_chat_stream_service import DetachedChatStreamService
from tests.conftest import make_auth_header

TENANT_A = "T_PUBCHAN_A"
TENANT_B = "T_PUBCHAN_B"
HEADERS_A = make_auth_header(TENANT_A)
HEADERS_B = make_auth_header(TENANT_B)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _create_agent(client: AsyncClient, headers: dict) -> int:
    resp = await client.post(
        "/api/v1/agents",
        json={"name": _unique("agent"), "description": "public-chan test"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_channel_bound_to(client: AsyncClient, headers: dict, agent_id: int) -> dict:
    """Create a channel and bind it to ``agent_id`` so its token can serve
    public chat / timeline requests for that agent."""
    resp = await client.post(
        "/api/v1/channels",
        json={"name": _unique("ch"), "agent_id": agent_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _set_welcome_message(
    client: AsyncClient, headers: dict, agent_id: int, content: str,
) -> None:
    resp = await client.put(
        f"/api/v1/agents/{agent_id}/engine-config",
        json={
            "conversation_settings": {
                "welcome_message": {
                    "enabled": True,
                    "blocks": [{"type": "markdown", "content": content}],
                }
            }
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def _set_ai_disclaimer(
    client: AsyncClient, headers: dict, agent_id: int, content: str,
) -> None:
    resp = await client.put(
        f"/api/v1/agents/{agent_id}/engine-config",
        json={
            "conversation_settings": {
                "ai_disclaimer": {
                    "enabled": True,
                    "content": content,
                }
            }
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def _create_conversation(client: AsyncClient, headers: dict, agent_id: int) -> dict:
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/conversations",
        json={"agent_id": agent_id, "user_id": "pub_test_user", "source": "chat"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestPublicChannelWelcomeMessage:

    @pytest.mark.asyncio
    async def test_public_channel_returns_agent_welcome_message_without_secrets(
        self, client: AsyncClient,
    ):
        agent_id = await _create_agent(client, HEADERS_A)
        await _set_welcome_message(
            client, HEADERS_A, agent_id, "欢迎使用公开渠道。"
        )
        channel = await _create_channel_bound_to(client, HEADERS_A, agent_id)

        resp = await client.get(f"/api/v1/public/channels/{channel['token']}")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "tenant_id" not in data
        assert "secret_key" not in data
        welcome = data["conversation_settings"]["welcome_message"]
        assert welcome["enabled"] is True
        assert welcome["blocks"] == [
            {"type": "markdown", "content": "欢迎使用公开渠道。"}
        ]

    @pytest.mark.asyncio
    async def test_public_channel_defaults_welcome_message_to_disabled(
        self, client: AsyncClient,
    ):
        agent_id = await _create_agent(client, HEADERS_A)
        channel = await _create_channel_bound_to(client, HEADERS_A, agent_id)

        resp = await client.get(f"/api/v1/public/channels/{channel['token']}")

        assert resp.status_code == 200, resp.text
        welcome = resp.json()["conversation_settings"]["welcome_message"]
        settings = resp.json()["conversation_settings"]
        assert welcome == {"enabled": False, "blocks": []}
        assert settings["ai_disclaimer"] == {
            "enabled": False,
            "content": "本内容由AI生成，仅供参考",
        }


class TestPublicChannelAIDisclaimer:

    @pytest.mark.asyncio
    async def test_public_channel_returns_agent_ai_disclaimer(
        self, client: AsyncClient,
    ):
        agent_id = await _create_agent(client, HEADERS_A)
        await _set_ai_disclaimer(
            client, HEADERS_A, agent_id, "AI 内容仅供参考，请自行判断。"
        )
        channel = await _create_channel_bound_to(client, HEADERS_A, agent_id)

        resp = await client.get(f"/api/v1/public/channels/{channel['token']}")

        assert resp.status_code == 200, resp.text
        disclaimer = resp.json()["conversation_settings"]["ai_disclaimer"]
        assert disclaimer == {
            "enabled": True,
            "content": "AI 内容仅供参考，请自行判断。",
        }


async def _seed_user_step(
    client: AsyncClient, headers: dict, agent_id: int, conv_id: int, content: str = "hi",
) -> None:
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/conversations/{conv_id}/steps",
        json={"round_number": 1, "step_type": "user_message", "content": content},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


class TestPublicConversationStepsOwnership:
    """Verify that a channel can only read conversations it actually owns
    (same tenant + same bound agent). Cross-tenant access must return 404
    so attackers can't tell "exists but forbidden" from "missing"."""

    @pytest.mark.asyncio
    async def test_owning_channel_can_read_its_conversation(self, client: AsyncClient):
        agent_id = await _create_agent(client, HEADERS_A)
        channel = await _create_channel_bound_to(client, HEADERS_A, agent_id)
        conv = await _create_conversation(client, HEADERS_A, agent_id)
        await _seed_user_step(client, HEADERS_A, agent_id, conv["id"], "owner reads ok")

        resp = await client.get(
            f"/api/v1/public/channels/{channel['token']}/conversations/{conv['id']}/steps"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["conversation_id"] == conv["id"]
        assert data["total_steps"] >= 1
        assert any(s["content"] == "owner reads ok" for s in data["steps"])

    @pytest.mark.asyncio
    async def test_other_tenant_channel_cannot_read_conversation_returns_404(
        self, client: AsyncClient,
    ):
        # Tenant A: agent + channel + conversation with at least one step.
        agent_a = await _create_agent(client, HEADERS_A)
        await _create_channel_bound_to(client, HEADERS_A, agent_a)
        conv_a = await _create_conversation(client, HEADERS_A, agent_a)
        await _seed_user_step(client, HEADERS_A, agent_a, conv_a["id"], "secret-of-A")

        # Tenant B: completely separate agent + channel; this token must NOT
        # be able to peek at tenant A's conversation just by guessing the id.
        agent_b = await _create_agent(client, HEADERS_B)
        channel_b = await _create_channel_bound_to(client, HEADERS_B, agent_b)

        resp = await client.get(
            f"/api/v1/public/channels/{channel_b['token']}/conversations/{conv_a['id']}/steps"
        )
        assert resp.status_code == 404, resp.text
        # Negative-leak check: response body must not contain any seeded
        # content from tenant A's conversation.
        assert "secret-of-A" not in resp.text

    @pytest.mark.asyncio
    async def test_same_tenant_other_agent_cannot_read_returns_404(
        self, client: AsyncClient,
    ):
        # Two agents in the SAME tenant, one channel bound to each. A
        # channel must only see conversations of the agent it's bound to,
        # even within its own tenant — otherwise tenants with multiple
        # public agents leak across them.
        agent_x = await _create_agent(client, HEADERS_A)
        agent_y = await _create_agent(client, HEADERS_A)
        channel_y = await _create_channel_bound_to(client, HEADERS_A, agent_y)
        conv_x = await _create_conversation(client, HEADERS_A, agent_x)
        await _seed_user_step(client, HEADERS_A, agent_x, conv_x["id"], "agent-x-only")

        resp = await client.get(
            f"/api/v1/public/channels/{channel_y['token']}/conversations/{conv_x['id']}/steps"
        )
        assert resp.status_code == 404, resp.text
        assert "agent-x-only" not in resp.text

    @pytest.mark.asyncio
    async def test_nonexistent_conversation_returns_404(self, client: AsyncClient):
        agent_id = await _create_agent(client, HEADERS_A)
        channel = await _create_channel_bound_to(client, HEADERS_A, agent_id)

        resp = await client.get(
            f"/api/v1/public/channels/{channel['token']}/conversations/9999999/steps"
        )
        assert resp.status_code == 404


class TestPublicChatOwnership:
    """The streaming chat endpoint accepts ``conversation_id`` in the body —
    without an ownership guard a leaked channel token could graft user /
    assistant steps onto another tenant's conversation, corrupting history
    and bypassing the timeline-ownership check.

    SSE responses always return HTTP 200; the engine's ``NotFoundError`` is
    caught by the router and re-emitted as an ``event: error`` SSE payload,
    so the assertions look at the response body, not the status code.
    """

    @staticmethod
    async def _list_conv_steps_admin(
        client: AsyncClient, headers: dict, agent_id: int, conv_id: int,
    ) -> list[dict]:
        """Pull the conversation timeline through the authenticated admin
        endpoint so we can assert no foreign step was inserted."""
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/{conv_id}/steps",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["steps"]

    @pytest.mark.asyncio
    async def test_chat_with_other_tenant_conversation_id_is_rejected(
        self, client: AsyncClient,
    ):
        # Tenant A: real conversation.
        agent_a = await _create_agent(client, HEADERS_A)
        await _create_channel_bound_to(client, HEADERS_A, agent_a)
        conv_a = await _create_conversation(client, HEADERS_A, agent_a)

        # Tenant B: separate channel attempting to write into A's conversation.
        agent_b = await _create_agent(client, HEADERS_B)
        channel_b = await _create_channel_bound_to(client, HEADERS_B, agent_b)

        marker = "ATTACK-MARKER-cross-tenant"
        resp = await client.post(
            f"/api/v1/public/channels/{channel_b['token']}/chat",
            json={"message": marker, "conversation_id": conv_a["id"]},
        )
        # SSE: status is always 200; the failure shows up in the body.
        assert resp.status_code == 200, resp.text
        assert "Conversation not found" in resp.text

        # The critical invariant: tenant A's conversation must NOT have
        # received any new user_message from this attempt.
        steps_a = await self._list_conv_steps_admin(
            client, HEADERS_A, agent_a, conv_a["id"],
        )
        assert all(
            (s.get("content") or "") != marker for s in steps_a
        ), f"foreign user_message leaked into conv_a: {steps_a}"

    @pytest.mark.asyncio
    async def test_chat_with_same_tenant_other_agent_conversation_id_is_rejected(
        self, client: AsyncClient,
    ):
        # Two agents in the same tenant; channel Y is bound to agent Y but the
        # request supplies a conversation that belongs to agent X.
        agent_x = await _create_agent(client, HEADERS_A)
        agent_y = await _create_agent(client, HEADERS_A)
        channel_y = await _create_channel_bound_to(client, HEADERS_A, agent_y)
        conv_x = await _create_conversation(client, HEADERS_A, agent_x)

        marker = "ATTACK-MARKER-cross-agent"
        resp = await client.post(
            f"/api/v1/public/channels/{channel_y['token']}/chat",
            json={"message": marker, "conversation_id": conv_x["id"]},
        )
        assert resp.status_code == 200, resp.text
        assert "Conversation not found" in resp.text

        # Agent X's conversation must remain untouched by agent Y's channel.
        steps_x = await self._list_conv_steps_admin(
            client, HEADERS_A, agent_x, conv_x["id"],
        )
        assert all(
            (s.get("content") or "") != marker for s in steps_x
        ), f"foreign user_message leaked into conv_x: {steps_x}"

    @pytest.mark.asyncio
    async def test_authenticated_chat_with_other_agents_conversation_is_rejected(
        self, client: AsyncClient,
    ):
        """Same guard, authenticated path. Tenant A holds agents X and Y;
        an API key with ``chat`` scope can hit either agent's chat endpoint,
        but it must not be allowed to point agent Y's chat at a conversation
        that belongs to agent X."""
        agent_x = await _create_agent(client, HEADERS_A)
        agent_y = await _create_agent(client, HEADERS_A)
        conv_x = await _create_conversation(client, HEADERS_A, agent_x)

        marker = "ATTACK-MARKER-auth-cross-agent"
        resp = await client.post(
            f"/api/v1/agents/{agent_y}/chat",
            json={"message": marker, "conversation_id": conv_x["id"]},
            headers=HEADERS_A,
        )
        assert resp.status_code == 200, resp.text
        assert "Conversation not found" in resp.text

        steps_x = await self._list_conv_steps_admin(
            client, HEADERS_A, agent_x, conv_x["id"],
        )
        assert all(
            (s.get("content") or "") != marker for s in steps_x
        ), f"foreign user_message leaked into conv_x via authenticated chat: {steps_x}"


class TestPublicChatTestFlag:
    @pytest.mark.asyncio
    async def test_public_chat_passes_test_context_without_echoing_it(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict = {}

        async def fake_get_channel_by_token(db, token: str):
            return SimpleNamespace(
                id=11,
                token=token,
                tenant_id=TENANT_A,
                agent_id=22,
                secret_key=None,
            )

        async def fake_get_agent_by_id(db, agent_id: int):
            return SimpleNamespace(id=agent_id, tenant_id=TENANT_A)

        async def fake_stream_public_chat(cls, **kwargs):
            captured.update(kwargs)
            yield (
                "event: conversation_created\n"
                'data: {"conversation_id": 123, "external_id": "conv_test"}\n\n'
            )

        monkeypatch.setattr(
            "app.routers.v1.public.ChannelService.get_by_token",
            fake_get_channel_by_token,
        )
        monkeypatch.setattr(
            "app.routers.v1.public.AgentService.get_by_id",
            fake_get_agent_by_id,
        )
        monkeypatch.setattr(
            DetachedChatStreamService,
            "stream_public_chat",
            classmethod(fake_stream_public_chat),
        )

        resp = await client.post(
            "/api/v1/public/channels/ch_test/chat",
            json={
                "message": "hello",
                "customer_context": {
                    "external_user_id": "test-user",
                    "source": "chat",
                    "channel_source": "official_site",
                    "is_test": True,
                },
            },
        )

        assert resp.status_code == 200, resp.text
        assert captured["customer_context"]["is_test"] is True
        assert captured["customer_context"]["source"] == "websdk"
        assert captured["customer_context"]["channel_id"] == 11
        assert captured["customer_context"]["channel_source"] == "official_site"
        assert "is_test" not in resp.text

    @pytest.mark.asyncio
    async def test_public_chat_preserves_channel_source_with_embed_token(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict = {}

        async def fake_get_channel_by_token(db, token: str):
            return SimpleNamespace(
                id=11,
                token=token,
                tenant_id=TENANT_A,
                agent_id=22,
                secret_key="secret",
            )

        async def fake_get_agent_by_id(db, agent_id: int):
            return SimpleNamespace(id=agent_id, tenant_id=TENANT_A)

        async def fake_stream_public_chat(cls, **kwargs):
            captured.update(kwargs)
            yield (
                "event: conversation_created\n"
                'data: {"conversation_id": 123, "external_id": "conv_test"}\n\n'
            )

        monkeypatch.setattr(
            "app.routers.v1.public.ChannelService.get_by_token",
            fake_get_channel_by_token,
        )
        monkeypatch.setattr(
            "app.routers.v1.public.AgentService.get_by_id",
            fake_get_agent_by_id,
        )
        monkeypatch.setattr(
            "app.routers.v1.public.verify_embed_token",
            lambda secret, token: {"external_user_id": "member", "source": "embed"},
        )
        monkeypatch.setattr(
            DetachedChatStreamService,
            "stream_public_chat",
            classmethod(fake_stream_public_chat),
        )

        resp = await client.post(
            "/api/v1/public/channels/ch_test/chat?embed_token=signed",
            json={
                "message": "hello",
                "customer_context": {
                    "channel_source": "wechat_mp",
                },
            },
        )

        assert resp.status_code == 200, resp.text
        assert captured["customer_context"]["external_user_id"] == "member"
        assert captured["customer_context"]["source"] == "websdk"
        assert captured["customer_context"]["channel_id"] == 11
        assert captured["customer_context"]["channel_source"] == "wechat_mp"
