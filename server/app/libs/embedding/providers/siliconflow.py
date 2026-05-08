"""
SiliconFlow embedding provider — calls SiliconFlow /v1/embeddings API.
"""
import httpx
import logging

from app.libs.embedding.base import BaseEmbeddingProvider
from app.configs.settings import settings

logger = logging.getLogger(__name__)

BGE_M3_DIMENSION = 1024


class SiliconFlowEmbeddingProvider(BaseEmbeddingProvider):
    """SiliconFlow embedding provider using bge-m3 model."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or settings.SILICONFLOW_API_KEY
        self._base_url = (base_url or settings.SILICONFLOW_BASE_URL).rstrip("/")
        self._model = model or settings.EMBEDDING_MODEL
        self._dimension = BGE_M3_DIMENSION

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
        payload = {
            "model": self._model,
            "input": texts,
            "encoding_format": "float",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]
