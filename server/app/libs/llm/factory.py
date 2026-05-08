"""
LLM provider factory — create LLM client instances.
"""
from app.libs.llm.base import BaseLLMClient


def create_llm_client() -> BaseLLMClient:
    """Create LLM client based on configuration.
    Uses LiteLLM with OpenRouter as the default provider.

    The returned instance is transparently wrapped with the observability
    layer's tracing decorator, so every chat/stream_chat call automatically
    emits a `genai.llm` span (OTel GenAI semantic convention) — no provider
    code changes required.
    """
    from app.libs.llm.providers.litellm_client import LiteLLMClient
    from app.libs.observability import wrap_llm_client

    return wrap_llm_client(LiteLLMClient())
