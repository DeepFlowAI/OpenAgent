"""
Reranker provider factory.
"""
from app.libs.knowledge_provider import resolve_reranker_provider
from app.libs.reranker.base import BaseRerankerProvider


def create_reranker_provider() -> BaseRerankerProvider:
    """Create reranker provider based on configuration."""
    provider = resolve_reranker_provider()
    if provider == "aliyun-bailian":
        from app.libs.reranker.providers.aliyun_bailian import (
            AliyunBailianRerankerProvider,
        )

        return AliyunBailianRerankerProvider()
    from app.libs.reranker.providers.siliconflow import SiliconFlowRerankerProvider

    return SiliconFlowRerankerProvider()
