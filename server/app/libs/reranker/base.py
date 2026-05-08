"""
Reranker provider protocol — abstract interface for re-ranking search results.
"""
from abc import ABC, abstractmethod


class BaseRerankerProvider(ABC):
    """Interface for reranker providers (SiliconFlow, Cohere, etc.)."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 10,
    ) -> list[dict]:
        """
        Re-rank documents by relevance to query.
        Returns list of dicts with 'index' and 'relevance_score', sorted by score desc.
        """
        ...
