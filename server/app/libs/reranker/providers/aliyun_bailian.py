"""
Alibaba Bailian reranker — DashScope text-rerank API (qwen3-vl-rerank, gte-rerank-v2).
"""
import httpx

from app.configs.settings import settings
from app.libs.reranker.base import BaseRerankerProvider


class AliyunBailianRerankerProvider(BaseRerankerProvider):
    """Bailian rerank via POST .../services/rerank/text-rerank/text-rerank."""

    def __init__(
        self,
        api_key: str | None = None,
        rerank_url: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or settings.ALIYUN_BAILIAN_API_KEY
        self._rerank_url = rerank_url or settings.ALIYUN_BAILIAN_RERANK_URL
        self._model = model or settings.RERANKER_MODEL

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 10,
    ) -> list[dict]:
        if not documents:
            return []

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self._model,
            "input": {
                "query": query,
                "documents": documents,
            },
            "parameters": {
                "return_documents": False,
                "top_n": min(top_n, len(documents)),
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self._rerank_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("output", {}).get("results", [])
        return sorted(results, key=lambda x: x["relevance_score"], reverse=True)
