"""
Integration tests for public knowledge OpenAPI endpoints.
"""
import time

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.document import Document


def _make_jwt_header(tenant_id: str) -> dict:
    token = create_access_token({
        "sub": "1",
        "tenant_id": tenant_id,
        "username": "admin",
        "role": "admin",
    })
    return {"Authorization": f"Bearer {token}"}


def _unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 100000}"


async def _create_api_key(client: AsyncClient, tenant_id: str, scopes: list[str]) -> str:
    response = await client.post(
        "/api/v1/system/api-keys",
        json={"name": _unique_name("key"), "scopes": scopes},
        headers=_make_jwt_header(tenant_id),
    )
    assert response.status_code == 201
    return response.json()["key_value"]


async def _create_kb(client: AsyncClient, tenant_id: str, name_prefix: str = "openapi-kb") -> int:
    response = await client.post(
        "/api/v1/knowledge-bases",
        json={
            "tenant_id": tenant_id,
            "name": _unique_name(name_prefix),
            "git_url": "https://github.com/example/openapi.git",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_document(kb_id: int, tenant_id: str) -> int:
    import app.db.session as session_mod

    async with session_mod.AsyncSessionLocal() as db:
        doc = Document(
            knowledge_base_id=kb_id,
            tenant_id=tenant_id,
            title="Guide",
            file_path="docs/guide.md",
            markdown_content="# Guide\n\nSecret body",
            doc_meta={"category": "guide"},
            slice_count=3,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc.id


class TestKnowledgeOpenAPI:

    @pytest.mark.asyncio
    async def test_list_knowledge_bases_uses_api_key_tenant(self, client: AsyncClient):
        tenant_a = "T_OPENAPI_A"
        tenant_b = "T_OPENAPI_B"
        kb_a = await _create_kb(client, tenant_a, "tenant-a")
        await _create_kb(client, tenant_b, "tenant-b")
        api_key = await _create_api_key(client, tenant_a, ["chat"])

        response = await client.get(
            "/api/v1/knowledge-bases",
            params={"tenant_id": tenant_b},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        items = response.json()["items"]
        ids = {item["id"] for item in items}
        assert kb_a in ids
        assert all("git_url" not in item for item in items)
        assert all("auth_token" not in item for item in items)

    @pytest.mark.asyncio
    async def test_list_knowledge_bases_requires_chat_scope(self, client: AsyncClient):
        api_key = await _create_api_key(client, "T_OPENAPI_SCOPE", ["config"])

        response = await client.get(
            "/api/v1/knowledge-bases",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_documents_returns_public_fields(self, client: AsyncClient):
        tenant_id = "T_OPENAPI_DOCS"
        kb_id = await _create_kb(client, tenant_id, "docs")
        doc_id = await _create_document(kb_id, tenant_id)
        api_key = await _create_api_key(client, tenant_id, ["chat"])

        response = await client.get(
            f"/api/v1/knowledge-bases/{kb_id}/documents",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["id"] == doc_id
        assert item["file_path"] == "docs/guide.md"
        assert item["title"] == "Guide"
        assert item["slice_count"] == 3
        assert item["doc_meta"] == {"category": "guide"}
        assert item["markdown_url"] == f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/markdown"
        assert "markdown_content" not in item
        assert "source_url" not in item

    @pytest.mark.asyncio
    async def test_list_documents_rejects_other_tenant_kb(self, client: AsyncClient):
        kb_id = await _create_kb(client, "T_OPENAPI_OWNER", "owner")
        api_key = await _create_api_key(client, "T_OPENAPI_CALLER", ["chat"])

        response = await client.get(
            f"/api/v1/knowledge-bases/{kb_id}/documents",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 404
