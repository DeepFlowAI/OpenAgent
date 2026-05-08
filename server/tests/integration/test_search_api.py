"""
Integration tests for Search API — aligned with AI搜索 api.md design spec.
Tests against real SiliconFlow Embedding & Reranker APIs.
"""
import time
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token

TENANT_ID = "T_TEST_SEARCH"


def unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 100000}"


def _make_jwt_header(tenant_id: str) -> dict:
    token = create_access_token({
        "sub": "1",
        "tenant_id": tenant_id,
        "username": "admin",
        "role": "admin",
    })
    return {"Authorization": f"Bearer {token}"}


_cached_api_key: str | None = None


async def _get_or_cache_api_key(client: AsyncClient) -> str:
    global _cached_api_key
    if _cached_api_key is None:
        jwt_headers = _make_jwt_header(TENANT_ID)
        resp = await client.get("/api/v1/system/api-key/full", headers=jwt_headers)
        assert resp.status_code == 200
        _cached_api_key = resp.json()["key_value"]
    return _cached_api_key


async def _create_kb_with_slices(client: AsyncClient) -> int:
    """Create a KB then insert test slices via sync or direct API."""
    payload = {
        "tenant_id": TENANT_ID,
        "name": unique_name("search-kb"),
        "git_url": "https://github.com/example/search.git",
    }
    resp = await client.post("/api/v1/knowledge-bases", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _auth_headers(client: AsyncClient) -> dict:
    key = await _get_or_cache_api_key(client)
    return {"Authorization": f"Bearer {key}"}


class TestSearchAPIBasic:
    """Basic search API contract tests (no real data needed)."""

    @pytest.mark.asyncio
    async def test_search_nonexistent_kb_returns_404(self, client: AsyncClient):
        headers = await _auth_headers(client)
        resp = await client.post(
            "/api/v1/knowledge-bases/99999/search",
            json={"query": "test"},
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_search_without_auth_returns_401(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/knowledge-bases/1/search",
            json={"query": "test"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_search_empty_kb_returns_empty(self, client: AsyncClient):
        headers = await _auth_headers(client)
        kb_id = await _create_kb_with_slices(client)
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb_id}/search",
            json={"query": "任务"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_search_missing_query_returns_422(self, client: AsyncClient):
        headers = await _auth_headers(client)
        kb_id = await _create_kb_with_slices(client)
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb_id}/search",
            json={},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_response_structure(self, client: AsyncClient):
        headers = await _auth_headers(client)
        kb_id = await _create_kb_with_slices(client)
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb_id}/search",
            json={"query": "test"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_search_bm25_mode(self, client: AsyncClient):
        headers = await _auth_headers(client)
        kb_id = await _create_kb_with_slices(client)
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb_id}/search",
            json={
                "query": "test",
                "search": {"mode": "bm25"},
            },
            headers=headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_search_with_filter_conditions(self, client: AsyncClient):
        headers = await _auth_headers(client)
        kb_id = await _create_kb_with_slices(client)
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb_id}/search",
            json={
                "query": "test",
                "filter": {
                    "doc_meta": [
                        {"field": "tags", "op": "contains", "value": "prd"}
                    ],
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_search_with_highlight(self, client: AsyncClient):
        headers = await _auth_headers(client)
        kb_id = await _create_kb_with_slices(client)
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb_id}/search",
            json={
                "query": "test",
                "highlight": {
                    "enabled": True,
                    "pre_tag": "<em>",
                    "post_tag": "</em>",
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_search_with_pagination(self, client: AsyncClient):
        headers = await _auth_headers(client)
        kb_id = await _create_kb_with_slices(client)
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb_id}/search",
            json={
                "query": "test",
                "pagination": {"limit": 5, "offset": 0},
            },
            headers=headers,
        )
        assert resp.status_code == 200


class TestEmbeddingProvider:
    """Test SiliconFlow embedding API (real calls)."""

    @pytest.mark.asyncio
    async def test_embed_single_text(self):
        from app.libs.embedding.factory import create_embedding_provider

        provider = create_embedding_provider()
        vector = await provider.embed_text("人工智能在医疗领域的应用")
        assert isinstance(vector, list)
        assert len(vector) == 1024
        assert all(isinstance(v, float) for v in vector)

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        from app.libs.embedding.factory import create_embedding_provider

        provider = create_embedding_provider()
        texts = [
            "人工智能在医疗领域可用于疾病诊断",
            "机器学习是人工智能的一个分支",
        ]
        vectors = await provider.embed_batch(texts)
        assert len(vectors) == 2
        assert len(vectors[0]) == 1024
        assert len(vectors[1]) == 1024

    @pytest.mark.asyncio
    async def test_embed_empty_batch(self):
        from app.libs.embedding.factory import create_embedding_provider

        provider = create_embedding_provider()
        vectors = await provider.embed_batch([])
        assert vectors == []


class TestRerankerProvider:
    """Test SiliconFlow reranker API (real calls)."""

    @pytest.mark.asyncio
    async def test_rerank_documents(self):
        from app.libs.reranker.factory import create_reranker_provider

        provider = create_reranker_provider()
        results = await provider.rerank(
            query="人工智能的应用场景",
            documents=[
                "人工智能在医疗领域可用于疾病诊断和药物研发",
                "机器学习是人工智能的一个分支",
                "今天的天气很好",
            ],
            top_n=3,
        )
        assert len(results) == 3
        assert all("index" in r and "relevance_score" in r for r in results)
        assert results[0]["relevance_score"] >= results[-1]["relevance_score"]
        weather_scores = [r for r in results if r["index"] == 2]
        assert weather_scores[0]["relevance_score"] < results[0]["relevance_score"]

    @pytest.mark.asyncio
    async def test_rerank_empty_documents(self):
        from app.libs.reranker.factory import create_reranker_provider

        provider = create_reranker_provider()
        results = await provider.rerank(
            query="test",
            documents=[],
            top_n=5,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_rerank_top_n(self):
        from app.libs.reranker.factory import create_reranker_provider

        provider = create_reranker_provider()
        results = await provider.rerank(
            query="密码重置",
            documents=[
                "如何重置密码",
                "登录失败怎么办",
                "修改个人信息",
                "密码安全策略",
            ],
            top_n=2,
        )
        assert len(results) == 2
