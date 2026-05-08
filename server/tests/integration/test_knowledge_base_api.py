"""
Integration tests for KnowledgeBase API
"""
import time
import pytest
from httpx import AsyncClient

TENANT_ID = "T_TEST_KB"


def unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 100000}"


class TestKnowledgeBaseAPI:

    @pytest.mark.asyncio
    async def test_list_knowledge_bases_returns_200(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/knowledge-bases", params={"tenant_id": TENANT_ID}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_create_knowledge_base_returns_201(self, client: AsyncClient):
        payload = {
            "tenant_id": TENANT_ID,
            "name": unique_name("create"),
            "description": "Test knowledge base",
            "git_url": "https://github.com/example/repo.git",
            "git_branch": "main",
            "auth_type": "none",
        }
        resp = await client.post("/api/v1/knowledge-bases", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["git_url"] == "https://github.com/example/repo.git"
        assert data["tenant_id"] == TENANT_ID

    @pytest.mark.asyncio
    async def test_create_duplicate_name_returns_400(self, client: AsyncClient):
        name = unique_name("dup")
        payload = {
            "tenant_id": TENANT_ID,
            "name": name,
            "git_url": "https://github.com/example/dup.git",
        }
        resp1 = await client.post("/api/v1/knowledge-bases", json=payload)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/knowledge-bases", json=payload)
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_get_knowledge_base_returns_200(self, client: AsyncClient):
        name = unique_name("get")
        payload = {
            "tenant_id": TENANT_ID,
            "name": name,
            "git_url": "https://github.com/example/get.git",
        }
        create_resp = await client.post("/api/v1/knowledge-bases", json=payload)
        kb_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == name

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/knowledge-bases/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_knowledge_base_returns_200(self, client: AsyncClient):
        name = unique_name("upd")
        payload = {
            "tenant_id": TENANT_ID,
            "name": name,
            "git_url": "https://github.com/example/update.git",
        }
        create_resp = await client.post("/api/v1/knowledge-bases", json=payload)
        kb_id = create_resp.json()["id"]

        new_name = unique_name("upd-new")
        update_payload = {"name": new_name, "description": "Updated desc"}
        resp = await client.put(
            f"/api/v1/knowledge-bases/{kb_id}", json=update_payload
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == new_name
        assert resp.json()["description"] == "Updated desc"

    @pytest.mark.asyncio
    async def test_delete_knowledge_base_returns_200(self, client: AsyncClient):
        name = unique_name("del")
        payload = {
            "tenant_id": TENANT_ID,
            "name": name,
            "git_url": "https://github.com/example/delete.git",
        }
        create_resp = await client.post("/api/v1/knowledge-bases", json=payload)
        kb_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/knowledge-bases/{kb_id}")
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_missing_required_field_returns_422(
        self, client: AsyncClient
    ):
        payload = {"tenant_id": TENANT_ID}
        resp = await client.post("/api/v1/knowledge-bases", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_token_auth(self, client: AsyncClient):
        payload = {
            "tenant_id": TENANT_ID,
            "name": unique_name("token"),
            "git_url": "https://github.com/example/private.git",
            "auth_type": "token",
            "auth_token": "ghp_testtoken123",
        }
        resp = await client.post("/api/v1/knowledge-bases", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["auth_type"] == "token"

    @pytest.mark.asyncio
    async def test_meta_schema_returns_200(self, client: AsyncClient):
        name = unique_name("schema")
        payload = {
            "tenant_id": TENANT_ID,
            "name": name,
            "git_url": "https://github.com/example/schema.git",
        }
        create_resp = await client.post("/api/v1/knowledge-bases", json=payload)
        kb_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/meta-schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "doc_meta" in data
        assert "slice_meta" in data
        assert isinstance(data["doc_meta"], list)
        assert isinstance(data["slice_meta"], list)

    @pytest.mark.asyncio
    async def test_meta_schema_nonexistent_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/knowledge-bases/99999/meta-schema")
        assert resp.status_code == 404
