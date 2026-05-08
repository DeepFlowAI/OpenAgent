"""
Reranker provider factory.
"""
from app.libs.reranker.base import BaseRerankerProvider


def create_reranker_provider() -> BaseRerankerProvider:
    """Create reranker provider based on configuration."""
    from app.libs.reranker.providers.siliconflow import SiliconFlowRerankerProvider
    return SiliconFlowRerankerProvider()
