"""
Integration tests for Conversation API
"""
import time
import pytest
from httpx import AsyncClient

from tests.conftest import make_auth_header

TENANT_ID = "T_TEST_CONV"
HEADERS = make_auth_header(TENANT_ID)


def unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 100000}"


async def _create_agent(client: AsyncClient) -> int:
    """Helper: create an agent and return its ID."""
    payload = {"name": unique_name("agent"), "description": "Agent for conversation tests"}
    resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_conversation(
    client: AsyncClient, agent_id: int, **overrides
) -> dict:
    """Helper: create a conversation and return its data."""
    payload = {
        "agent_id": agent_id,
        "user_id": "test_user_001",
        "source": "chat",
        **overrides,
    }
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/conversations", json=payload, headers=HEADERS
    )
    assert resp.status_code == 201
    return resp.json()


class TestConversationAPI:

    @pytest.mark.asyncio
    async def test_list_conversations_returns_200(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data

    @pytest.mark.asyncio
    async def test_create_conversation_returns_201(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        data = await _create_conversation(client, agent_id)
        assert data["agent_id"] == agent_id
        assert data["tenant_id"] == TENANT_ID
        assert data["status"] == "active"
        assert data["source"] == "chat"
        assert data["external_id"].startswith("conv_")
        assert data["round_count"] == 0
        assert data["total_tokens"] == 0

    @pytest.mark.asyncio
    async def test_create_conversation_api_source(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        data = await _create_conversation(client, agent_id, source="api")
        assert data["source"] == "api"

    @pytest.mark.asyncio
    async def test_get_conversation_returns_200(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        created = await _create_conversation(client, agent_id)
        conv_id = created["id"]

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/{conv_id}", headers=HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == conv_id
        assert "duration_seconds" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_conversation_returns_404(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/99999", headers=HEADERS
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_end_conversation(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        created = await _create_conversation(client, agent_id)
        conv_id = created["id"]

        resp = await client.post(
            f"/api/v1/agents/{agent_id}/conversations/{conv_id}/end", headers=HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ended"
        assert data["ended_at"] is not None

    @pytest.mark.asyncio
    async def test_filter_by_status(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        created = await _create_conversation(client, agent_id)
        conv_id = created["id"]

        await client.post(
            f"/api/v1/agents/{agent_id}/conversations/{conv_id}/end", headers=HEADERS
        )

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            params={"status_filter": "ended"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["status"] == "ended"

    @pytest.mark.asyncio
    async def test_filter_by_source(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        await _create_conversation(client, agent_id, source="api")

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            params={"source": "api"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["source"] == "api"

    @pytest.mark.asyncio
    async def test_filter_by_conversation_id(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        created = await _create_conversation(client, agent_id)
        external_id = created["external_id"]

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            params={"conversation_id": external_id},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["external_id"] == external_id

    @pytest.mark.asyncio
    async def test_create_missing_required_field_returns_422(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        resp = await client.post(
            f"/api/v1/agents/{agent_id}/conversations", json={}, headers=HEADERS
        )
        assert resp.status_code == 422
