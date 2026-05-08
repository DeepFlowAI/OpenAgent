import redis.asyncio as aioredis

from app.configs.settings import settings


class RedisClient:
    """Lazy-init async Redis wrapper."""

    def __init__(self):
        self._client: aioredis.Redis | None = None

    async def initialize(self) -> None:
        if settings.REDIS_URL:
            self._client = aioredis.from_url(
                settings.REDIS_URL, decode_responses=True
            )

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("Redis not initialized. Set REDIS_URL to enable.")
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


redis_client = RedisClient()
