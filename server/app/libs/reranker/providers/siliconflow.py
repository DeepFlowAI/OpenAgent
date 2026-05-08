"""
SiliconFlow reranker provider — calls SiliconFlow /v1/rerank API.
"""
import httpx
import logging

from app.libs.reranker.base import BaseRerankerProvider
from app.configs.settings import settings

logger = logging.getLogger(__name__)


class SiliconFlowRerankerProvider(BaseRerankerProvider):
    """SiliconFlow reranker using bge-reranker-v2-m3 model."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or settings.SILICONFLOW_API_KEY
        self._base_url = (base_url or settings.SILICONFLOW_BASE_URL).rstrip("/")
        self._model = model or settings.RERANKER_MODEL

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 10,
    ) -> list[dict]:
        if not documents:
            return []

        url = f"{self._base_url}/rerank"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "return_documents": False,
            "top_n": min(top_n, len(documents)),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        return sorted(results, key=lambda x: x["relevance_score"], reverse=True)
