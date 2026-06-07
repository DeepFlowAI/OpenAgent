"""
SiliconFlow embedding provider — calls SiliconFlow /v1/embeddings API.

Resilience: the primary model is retried a few times on failure, and if it
keeps failing the provider fails over to a backup model on the same provider
(e.g. ``Pro/BAAI/bge-m3`` → ``BAAI/bge-m3``). Both models share the same
vector space, so the cached document embeddings stay comparable.
"""
import httpx
import logging

from app.libs.embedding.base import BaseEmbeddingProvider
from app.configs.settings import settings

logger = logging.getLogger(__name__)

BGE_M3_DIMENSION = 1024
# Per-model attempt budget: how many times each model is tried (immediate
# retries, no backoff) before giving up on it.
EMBED_MAX_ATTEMPTS = 3


class SiliconFlowEmbeddingProvider(BaseEmbeddingProvider):
    """SiliconFlow embedding provider using bge-m3 model."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
    ):
        self._api_key = api_key or settings.SILICONFLOW_API_KEY
        self._base_url = (base_url or settings.SILICONFLOW_BASE_URL).rstrip("/")
        self._model = model or settings.EMBEDDING_MODEL
        self._fallback_model = (
            fallback_model
            if fallback_model is not None
            else settings.EMBEDDING_FALLBACK_MODEL
        )
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

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                return await self._embed_with_retries(client, self._model, texts)
            except Exception as primary_exc:  # noqa: BLE001
                if not self._fallback_model or self._fallback_model == self._model:
                    raise
                logger.error(
                    "Embedding primary model failed after %d attempts, failing "
                    "over to backup — primary=%s backup=%s texts=%d last_error=%r",
                    EMBED_MAX_ATTEMPTS,
                    self._model,
                    self._fallback_model,
                    len(texts),
                    primary_exc,
                )
                vectors = await self._embed_with_retries(
                    client, self._fallback_model, texts
                )
                logger.warning(
                    "Embedding served by BACKUP model — backup=%s texts=%d "
                    "(primary=%s is degraded)",
                    self._fallback_model,
                    len(texts),
                    self._model,
                )
                return vectors

    async def _embed_with_retries(
        self, client: httpx.AsyncClient, model: str, texts: list[str]
    ) -> list[list[float]]:
        last_exc: Exception | None = None
        for attempt in range(1, EMBED_MAX_ATTEMPTS + 1):
            try:
                return await self._embed_once(client, model, texts)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.error(
                    "Embedding attempt %d/%d failed — model=%s texts=%d error=%r",
                    attempt,
                    EMBED_MAX_ATTEMPTS,
                    model,
                    len(texts),
                    exc,
                )
        assert last_exc is not None
        raise last_exc

    async def _embed_once(
        self, client: httpx.AsyncClient, model: str, texts: list[str]
    ) -> list[list[float]]:
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": model,
            "input": texts,
            "encoding_format": "float",
        }
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]
