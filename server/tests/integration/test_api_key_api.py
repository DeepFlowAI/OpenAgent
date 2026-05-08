"""
Integration tests for API Key endpoints (legacy + multi-key)
"""
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _make_auth_header(tenant_id: str = "T_TEST_001") -> dict:
    token = create_access_token({
        "sub": "1",
        "tenant_id": tenant_id,
        "username": "admin",
        "role": "admin",
    })
    return {"Authorization": f"Bearer {token}"}


class TestLegacyApiKeyAPI:

    @pytest.mark.asyncio
    async def test_get_api_key_auto_creates(self, client: AsyncClient):
        headers = _make_auth_header("T_APIKEY_01")
        resp = await client.get("/api/v1/system/api-key", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "masked_key" in data
        assert data["masked_key"].startswith("sk-")
        assert "••••" in data["masked_key"]

    @pytest.mark.asyncio
    async def test_get_api_key_returns_same_key(self, client: AsyncClient):
        headers = _make_auth_header("T_APIKEY_02")
        resp1 = await client.get("/api/v1/system/api-key", headers=headers)
        resp2 = await client.get("/api/v1/system/api-key", headers=headers)
        assert resp1.json()["masked_key"] == resp2.json()["masked_key"]

    @pytest.mark.asyncio
    async def test_get_full_key_returns_complete_key(self, client: AsyncClient):
        headers = _make_auth_header("T_APIKEY_03")
        await client.get("/api/v1/system/api-key", headers=headers)
        resp = await client.get("/api/v1/system/api-key/full", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["key_value"].startswith("sk-")
        assert "••••" not in data["key_value"]
        assert len(data["key_value"]) == 51

    @pytest.mark.asyncio
    async def test_reset_key_changes_key(self, client: AsyncClient):
        headers = _make_auth_header("T_APIKEY_04")
        resp_before = await client.get("/api/v1/system/api-key/full", headers=headers)
        old_key = resp_before.json()["key_value"]

        resp_reset = await client.post("/api/v1/system/api-key/reset", headers=headers)
        assert resp_reset.status_code == 200
        assert "masked_key" in resp_reset.json()

        resp_after = await client.get("/api/v1/system/api-key/full", headers=headers)
        new_key = resp_after.json()["key_value"]
        assert old_key != new_key

    @pytest.mark.asyncio
    async def test_get_api_key_without_auth_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/system/api-key")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_api_key_with_invalid_token_returns_401(self, client: AsyncClient):
        headers = {"Authorization": "Bearer invalid-token"}
        resp = await client.get("/api/v1/system/api-key", headers=headers)
        assert resp.status_code == 401


class TestMultiKeyApiKeyAPI:

    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_EMPTY")
        resp = await client.get("/api/v1/system/api-keys", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_create_api_key_returns_201(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_01")
        payload = {"name": "Test Key", "scopes": ["chat"]}
        resp = await client.post("/api/v1/system/api-keys", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Key"
        assert data["scopes"] == ["chat"]
        assert data["status"] == "active"
        assert "key_value" in data
        assert data["key_value"].startswith("sk-")
        assert "masked_key" in data

    @pytest.mark.asyncio
    async def test_create_api_key_with_all_scopes(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_02")
        payload = {"name": "Full Access", "scopes": ["chat", "config"], "description": "All scopes"}
        resp = await client.post("/api/v1/system/api-keys", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert set(data["scopes"]) == {"chat", "config"}
        assert data["description"] == "All scopes"

    @pytest.mark.asyncio
    async def test_create_api_key_invalid_scope_returns_400(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_03")
        payload = {"name": "Bad Scope", "scopes": ["admin"]}
        resp = await client.post("/api/v1/system/api-keys", json=payload, headers=headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_api_key_missing_name_returns_422(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_04")
        payload = {"scopes": ["chat"]}
        resp = await client.post("/api/v1/system/api-keys", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_api_keys_returns_created(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_05")
        await client.post(
            "/api/v1/system/api-keys",
            json={"name": "Key A", "scopes": ["chat"]},
            headers=headers,
        )
        await client.post(
            "/api/v1/system/api-keys",
            json={"name": "Key B", "scopes": ["chat", "config"]},
            headers=headers,
        )

        resp = await client.get("/api/v1/system/api-keys", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        names = {item["name"] for item in data["items"]}
        assert "Key A" in names
        assert "Key B" in names
        for item in data["items"]:
            assert "key_value" not in item

    @pytest.mark.asyncio
    async def test_rotate_api_key(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_06")
        create_resp = await client.post(
            "/api/v1/system/api-keys",
            json={"name": "Rotate Me", "scopes": ["chat"]},
            headers=headers,
        )
        key_id = create_resp.json()["id"]
        old_key = create_resp.json()["key_value"]

        rotate_resp = await client.post(
            f"/api/v1/system/api-keys/{key_id}/rotate",
            headers=headers,
        )
        assert rotate_resp.status_code == 200
        data = rotate_resp.json()
        assert data["key_value"].startswith("sk-")
        assert data["key_value"] != old_key
        assert data["name"] == "Rotate Me"

    @pytest.mark.asyncio
    async def test_rotate_nonexistent_key_returns_404(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_07")
        resp = await client.post(
            "/api/v1/system/api-keys/99999/rotate",
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_08")
        create_resp = await client.post(
            "/api/v1/system/api-keys",
            json={"name": "Revoke Me", "scopes": ["chat"]},
            headers=headers,
        )
        key_id = create_resp.json()["id"]

        revoke_resp = await client.delete(
            f"/api/v1/system/api-keys/{key_id}",
            headers=headers,
        )
        assert revoke_resp.status_code == 200

        list_resp = await client.get("/api/v1/system/api-keys", headers=headers)
        assert list_resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key_returns_404(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_09")
        resp = await client.delete(
            "/api/v1/system/api-keys/99999",
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_rotate_returns_404(self, client: AsyncClient):
        headers_a = _make_auth_header("T_CROSS_A")
        headers_b = _make_auth_header("T_CROSS_B")
        create_resp = await client.post(
            "/api/v1/system/api-keys",
            json={"name": "Tenant A Key", "scopes": ["chat"]},
            headers=headers_a,
        )
        key_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/system/api-keys/{key_id}/rotate",
            headers=headers_b,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_revoke_returns_404(self, client: AsyncClient):
        headers_a = _make_auth_header("T_CROSS_C")
        headers_b = _make_auth_header("T_CROSS_D")
        create_resp = await client.post(
            "/api/v1/system/api-keys",
            json={"name": "Tenant C Key", "scopes": ["chat"]},
            headers=headers_a,
        )
        key_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/system/api-keys/{key_id}",
            headers=headers_b,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_full_multi_key_matches_create(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_FULL")
        create_resp = await client.post(
            "/api/v1/system/api-keys",
            json={"name": "Copy Me", "scopes": ["chat"]},
            headers=headers,
        )
        assert create_resp.status_code == 201
        key_id = create_resp.json()["id"]
        expected = create_resp.json()["key_value"]

        full_resp = await client.get(
            f"/api/v1/system/api-keys/{key_id}/full",
            headers=headers,
        )
        assert full_resp.status_code == 200
        body = full_resp.json()
        assert body["key_value"] == expected
        assert "•" not in body["key_value"]

    @pytest.mark.asyncio
    async def test_get_full_nonexistent_key_returns_404(self, client: AsyncClient):
        headers = _make_auth_header("T_MULTI_FULL404")
        resp = await client.get(
            "/api/v1/system/api-keys/99999/full",
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_get_full_returns_404(self, client: AsyncClient):
        headers_a = _make_auth_header("T_FULL_A")
        headers_b = _make_auth_header("T_FULL_B")
        create_resp = await client.post(
            "/api/v1/system/api-keys",
            json={"name": "A", "scopes": ["chat"]},
            headers=headers_a,
        )
        key_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/v1/system/api-keys/{key_id}/full",
            headers=headers_b,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_without_auth_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/system/api-keys")
        assert resp.status_code == 401
