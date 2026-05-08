"""
Embedding provider factory.
"""
from app.libs.embedding.base import BaseEmbeddingProvider
from app.configs.settings import settings


def create_embedding_provider() -> BaseEmbeddingProvider:
    """Create embedding provider based on configuration."""
    from app.libs.embedding.providers.siliconflow import SiliconFlowEmbeddingProvider
    return SiliconFlowEmbeddingProvider()
