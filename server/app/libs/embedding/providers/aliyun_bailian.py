"""
Alibaba Bailian embedding provider — OpenAI-compatible /v1/embeddings API.
"""
import httpx

from app.configs.settings import settings
from app.libs.embedding.base import BaseEmbeddingProvider


class AliyunBailianEmbeddingProvider(BaseEmbeddingProvider):
    """Bailian text-embedding-v4 (and other compatible embedding models)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
    ):
        self._api_key = api_key or settings.ALIYUN_BAILIAN_API_KEY
        self._base_url = (base_url or settings.ALIYUN_BAILIAN_BASE_URL).rstrip("/")
        self._model = model or settings.EMBEDDING_MODEL
        self._dimension = dimension if dimension is not None else settings.EMBEDDING_DIMENSION

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload: dict = {
            "model": self._model,
            "input": texts,
            "encoding_format": "float",
        }
        if self._model.startswith("text-embedding-v"):
            payload["dimensions"] = self._dimension

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]
