"""
Embedding provider protocol — abstract interface for text-to-vector conversion.
"""
from abc import ABC, abstractmethod


class BaseEmbeddingProvider(ABC):
    """Interface for embedding providers (SiliconFlow, OpenAI, etc.)."""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Convert a single text to a vector."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Convert multiple texts to vectors."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension (e.g. 1024 for bge-m3)."""
        ...
