"""Resolve embedding / reranker backend from env."""

from __future__ import annotations

from app.configs.settings import settings

VALID_KNOWLEDGE_PROVIDERS = frozenset({"siliconflow", "aliyun-bailian"})


def resolve_knowledge_provider(explicit: str) -> str:
    """Pick provider name. Empty explicit → siliconflow if keyed, else bailian."""
    name = (explicit or "").strip().lower()
    if name:
        if name not in VALID_KNOWLEDGE_PROVIDERS:
            raise ValueError(
                f"Unknown knowledge provider {name!r}; "
                f"expected one of {sorted(VALID_KNOWLEDGE_PROVIDERS)}"
            )
        return name
    if settings.SILICONFLOW_API_KEY:
        return "siliconflow"
    if settings.ALIYUN_BAILIAN_API_KEY:
        return "aliyun-bailian"
    return "siliconflow"


def resolve_embedding_provider() -> str:
    return resolve_knowledge_provider(settings.EMBEDDING_PROVIDER)


def resolve_reranker_provider() -> str:
    return resolve_knowledge_provider(settings.RERANKER_PROVIDER)


def has_embedding_credentials() -> bool:
    provider = resolve_embedding_provider()
    if provider == "siliconflow":
        return bool(settings.SILICONFLOW_API_KEY)
    return bool(settings.ALIYUN_BAILIAN_API_KEY)
