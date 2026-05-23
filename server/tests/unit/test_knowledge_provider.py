"""Unit tests for knowledge-base provider selection and Bailian adapters."""

from unittest.mock import AsyncMock, patch

import pytest

from app.libs import knowledge_provider
from app.libs.embedding.factory import create_embedding_provider
from app.libs.embedding.providers.aliyun_bailian import AliyunBailianEmbeddingProvider
from app.libs.embedding.providers.siliconflow import SiliconFlowEmbeddingProvider
from app.libs.reranker.factory import create_reranker_provider
from app.libs.reranker.providers.aliyun_bailian import AliyunBailianRerankerProvider
from app.libs.reranker.providers.siliconflow import SiliconFlowRerankerProvider


def test_resolve_embedding_provider_explicit(monkeypatch):
    monkeypatch.setattr(knowledge_provider.settings, "EMBEDDING_PROVIDER", "aliyun-bailian")
    assert knowledge_provider.resolve_embedding_provider() == "aliyun-bailian"


def test_resolve_embedding_provider_auto_prefers_siliconflow(monkeypatch):
    monkeypatch.setattr(knowledge_provider.settings, "EMBEDDING_PROVIDER", "")
    monkeypatch.setattr(knowledge_provider.settings, "SILICONFLOW_API_KEY", "sf-key")
    monkeypatch.setattr(knowledge_provider.settings, "ALIYUN_BAILIAN_API_KEY", "bl-key")
    assert knowledge_provider.resolve_embedding_provider() == "siliconflow"


def test_resolve_embedding_provider_auto_bailian_when_no_siliconflow(monkeypatch):
    monkeypatch.setattr(knowledge_provider.settings, "EMBEDDING_PROVIDER", "")
    monkeypatch.setattr(knowledge_provider.settings, "SILICONFLOW_API_KEY", "")
    monkeypatch.setattr(knowledge_provider.settings, "ALIYUN_BAILIAN_API_KEY", "bl-key")
    assert knowledge_provider.resolve_embedding_provider() == "aliyun-bailian"


def test_create_embedding_provider_factory(monkeypatch):
    monkeypatch.setattr(knowledge_provider.settings, "EMBEDDING_PROVIDER", "aliyun-bailian")
    assert isinstance(create_embedding_provider(), AliyunBailianEmbeddingProvider)

    monkeypatch.setattr(knowledge_provider.settings, "EMBEDDING_PROVIDER", "siliconflow")
    assert isinstance(create_embedding_provider(), SiliconFlowEmbeddingProvider)


def test_create_reranker_provider_factory(monkeypatch):
    monkeypatch.setattr(knowledge_provider.settings, "RERANKER_PROVIDER", "aliyun-bailian")
    assert isinstance(create_reranker_provider(), AliyunBailianRerankerProvider)

    monkeypatch.setattr(knowledge_provider.settings, "RERANKER_PROVIDER", "siliconflow")
    assert isinstance(create_reranker_provider(), SiliconFlowRerankerProvider)


@pytest.mark.asyncio
async def test_bailian_embedding_parses_openai_compatible_response():
    provider = AliyunBailianEmbeddingProvider(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="text-embedding-v4",
        dimension=1024,
    )
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "data": [
            {"index": 1, "embedding": [0.2, 0.3]},
            {"index": 0, "embedding": [0.1, 0.2]},
        ]
    }

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as post:
        vectors = await provider.embed_batch(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.2, 0.3]]
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "text-embedding-v4"
    assert payload["dimensions"] == 1024


@pytest.mark.asyncio
async def test_bailian_rerank_parses_dashscope_response():
    provider = AliyunBailianRerankerProvider(
        api_key="test-key",
        rerank_url="https://example.com/rerank",
        model="qwen3-vl-rerank",
    )
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {
        "output": {
            "results": [
                {"index": 2, "relevance_score": 0.34},
                {"index": 0, "relevance_score": 0.95},
            ]
        }
    }

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        results = await provider.rerank("query", ["d0", "d1", "d2"], top_n=2)

    assert results == [
        {"index": 0, "relevance_score": 0.95},
        {"index": 2, "relevance_score": 0.34},
    ]
