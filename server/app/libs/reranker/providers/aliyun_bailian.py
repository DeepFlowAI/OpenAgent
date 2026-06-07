"""
Alibaba Bailian reranker — DashScope text-rerank API (qwen3-vl-rerank, gte-rerank-v2).
"""
import httpx

from app.configs.settings import settings
from app.libs.reranker.base import BaseRerankerProvider

# DashScope text-rerank hard limits (verified against the live API). Violating
# any of them makes the API reject the WHOLE batch with HTTP 400, so we sanitize
# the input before sending instead of letting one bad document fail every search:
#   - documents count must be 1..500
#   - each document must be 1..8000 characters (empty string is also rejected)
_MAX_DOCS_PER_BATCH = 500
_MAX_DOC_CHARS = 8000


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

        # Sanitize for DashScope limits while keeping a map back to the caller's
        # original indices: drop empty docs, truncate over-long ones. The returned
        # ``index`` must stay relative to ``documents`` (the caller maps it back to
        # its own items), and truncation only affects scoring — callers use their
        # own original content, so it is invisible downstream.
        prepared: list[tuple[int, str]] = []
        for original_index, doc in enumerate(documents):
            text = (doc or "").strip()
            if not text:
                continue
            if len(text) > _MAX_DOC_CHARS:
                text = text[:_MAX_DOC_CHARS]
            prepared.append((original_index, text))
        if not prepared:
            return []

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        merged: list[dict] = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for start in range(0, len(prepared), _MAX_DOCS_PER_BATCH):
                batch = prepared[start:start + _MAX_DOCS_PER_BATCH]
                payload = {
                    "model": self._model,
                    "input": {
                        "query": query,
                        "documents": [text for _, text in batch],
                    },
                    "parameters": {
                        # Ask for every score so the global top_n is correct even
                        # when documents are split across multiple batches.
                        "return_documents": False,
                        "top_n": len(batch),
                    },
                }
                resp = await client.post(
                    self._rerank_url, json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                for r in data.get("output", {}).get("results", []):
                    r["index"] = batch[r["index"]][0]  # batch-local → original
                    merged.append(r)

        merged.sort(key=lambda x: x["relevance_score"], reverse=True)
        return merged[:top_n]
