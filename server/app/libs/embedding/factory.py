"""
Embedding provider factory.
"""
from app.libs.embedding.base import BaseEmbeddingProvider
from app.libs.knowledge_provider import resolve_embedding_provider


def create_embedding_provider() -> BaseEmbeddingProvider:
    """Create embedding provider based on configuration."""
    provider = resolve_embedding_provider()
    if provider == "aliyun-bailian":
        from app.libs.embedding.providers.aliyun_bailian import (
            AliyunBailianEmbeddingProvider,
        )

        return AliyunBailianEmbeddingProvider()
    from app.libs.embedding.providers.siliconflow import SiliconFlowEmbeddingProvider

    return SiliconFlowEmbeddingProvider()
