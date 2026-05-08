"""
Integration tests for Agent API
"""
import time
import pytest
from httpx import AsyncClient

from tests.conftest import make_auth_header

TENANT_ID = "T_TEST_AGENT"
HEADERS = make_auth_header(TENANT_ID)


def unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 100000}"


class TestAgentAPI:

    @pytest.mark.asyncio
    async def test_list_agents_returns_200(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/agents",
            params={"status_filter": "active"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_create_agent_returns_201(self, client: AsyncClient):
        payload = {
            "name": unique_name("create"),
            "description": "Test agent",
        }
        resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["tenant_id"] == TENANT_ID
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_duplicate_name_returns_400(self, client: AsyncClient):
        name = unique_name("dup")
        payload = {"name": name}
        resp1 = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_create_blank_name_returns_400(self, client: AsyncClient):
        payload = {"name": "   "}
        resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_agent_returns_200(self, client: AsyncClient):
        name = unique_name("get")
        payload = {"name": name}
        create_resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        agent_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/agents/{agent_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["name"] == name

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/agents/99999", headers=HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_agent_returns_200(self, client: AsyncClient):
        name = unique_name("upd")
        payload = {"name": name}
        create_resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        agent_id = create_resp.json()["id"]

        new_name = unique_name("upd-new")
        update_payload = {"name": new_name, "description": "Updated desc"}
        resp = await client.put(f"/api/v1/agents/{agent_id}", json=update_payload, headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["name"] == new_name
        assert resp.json()["description"] == "Updated desc"

    @pytest.mark.asyncio
    async def test_disable_agent_returns_200(self, client: AsyncClient):
        name = unique_name("dis")
        payload = {"name": name}
        create_resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        agent_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/agents/{agent_id}/status", json={"status": "inactive"}, headers=HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "inactive"

    @pytest.mark.asyncio
    async def test_enable_agent_returns_200(self, client: AsyncClient):
        name = unique_name("ena")
        payload = {"name": name}
        create_resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        agent_id = create_resp.json()["id"]

        await client.put(
            f"/api/v1/agents/{agent_id}/status", json={"status": "inactive"}, headers=HEADERS
        )
        resp = await client.put(
            f"/api/v1/agents/{agent_id}/status", json={"status": "active"}, headers=HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_list_inactive_agents(self, client: AsyncClient):
        name = unique_name("inact")
        payload = {"name": name}
        create_resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        agent_id = create_resp.json()["id"]

        await client.put(
            f"/api/v1/agents/{agent_id}/status", json={"status": "inactive"}, headers=HEADERS
        )

        resp = await client.get(
            "/api/v1/agents",
            params={"status_filter": "inactive"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_create_missing_required_field_returns_422(
        self, client: AsyncClient
    ):
        payload = {}
        resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
        assert resp.status_code == 422
