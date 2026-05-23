"""
Integration tests for Channel API
"""
import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import make_auth_header

TENANT_ID = "T_TEST_CHAN"
HEADERS = make_auth_header(TENANT_ID)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TestChannelAPI:

    @pytest.mark.asyncio
    async def test_list_channels_returns_200(self, client: AsyncClient):
        resp = await client.get("/api/v1/channels", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_create_channel_returns_201(self, client: AsyncClient):
        name = _unique("ch-create")
        payload = {
            "name": name,
            "description": "integration test",
        }
        resp = await client.post("/api/v1/channels", json=payload, headers=HEADERS)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == name
        assert data["channel_type"] == "web-sdk"
        assert data["access_mode"] == "url"

    @pytest.mark.asyncio
    async def test_create_channel_missing_name_returns_422(self, client: AsyncClient):
        payload = {}
        resp = await client.post("/api/v1/channels", json=payload, headers=HEADERS)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_channel_duplicate_name_returns_400(self, client: AsyncClient):
        name = _unique("ch-dup")
        payload = {"name": name}
        resp1 = await client.post("/api/v1/channels", json=payload, headers=HEADERS)
        assert resp1.status_code == 201

        resp2 = await client.post("/api/v1/channels", json=payload, headers=HEADERS)
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_get_channel_returns_200(self, client: AsyncClient):
        name = _unique("ch-get")
        create_resp = await client.post(
            "/api/v1/channels",
            json={"name": name},
            headers=HEADERS,
        )
        channel_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/channels/{channel_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["name"] == name

    @pytest.mark.asyncio
    async def test_get_channel_not_found_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/channels/99999", headers=HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_channel_returns_200(self, client: AsyncClient):
        name = _unique("ch-update")
        create_resp = await client.post(
            "/api/v1/channels",
            json={"name": name},
            headers=HEADERS,
        )
        channel_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/channels/{channel_id}",
            json={"description": "updated desc", "access_mode": "embed"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "updated desc"
        assert resp.json()["access_mode"] == "embed"

    @pytest.mark.asyncio
    async def test_update_channel_same_page_allowlist_normalizes_patterns(
        self, client: AsyncClient
    ):
        name = _unique("ch-allowlist")
        create_resp = await client.post(
            "/api/v1/channels",
            json={"name": name},
            headers=HEADERS,
        )
        channel_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/channels/{channel_id}",
            json={
                "config": {
                    "samePageNavigationUrlAllowlist": [
                        "  HTTPS://Login.EXAMPLE.com/*  ",
                        "",
                        "https://login.example.com/*",
                        "https://*.example.com/oauth/*",
                    ]
                }
            },
            headers=HEADERS,
        )

        assert resp.status_code == 200
        assert resp.json()["config"]["samePageNavigationUrlAllowlist"] == [
            "https://login.example.com/*",
            "https://*.example.com/oauth/*",
        ]

    @pytest.mark.asyncio
    async def test_update_channel_same_page_allowlist_rejects_invalid_patterns(
        self, client: AsyncClient
    ):
        name = _unique("ch-allowlist-invalid")
        create_resp = await client.post(
            "/api/v1/channels",
            json={"name": name},
            headers=HEADERS,
        )
        channel_id = create_resp.json()["id"]

        for pattern in ["https://*", "javascript:*"]:
            resp = await client.put(
                f"/api/v1/channels/{channel_id}",
                json={"config": {"samePageNavigationUrlAllowlist": [pattern]}},
                headers=HEADERS,
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_channel_returns_200(self, client: AsyncClient):
        name = _unique("ch-delete")
        create_resp = await client.post(
            "/api/v1/channels",
            json={"name": name},
            headers=HEADERS,
        )
        channel_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/channels/{channel_id}", headers=HEADERS)
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/v1/channels/{channel_id}", headers=HEADERS)
        assert get_resp.status_code == 404
