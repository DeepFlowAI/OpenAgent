"""
LiteLLM-based LLM provider — routes requests through multiple upstreams
using the LiteLLM SDK for unified model access.

Reliability (aligned with AgentEngine: SSE streaming, tool loop, single user-selected model):
- num_retries: retry the same model on transient failures only (LiteLLM); no automatic model fallback,
  so billing/behavior stay predictable vs the UI selection.
- Domestic model routing uses explicit provider fallback:
  Alibaba Bailian -> model official -> SiliconFlow -> OpenRouter.
- Optional request timeout via settings to cap hung upstream calls without affecting retry count logic.
- Stream-level reliability (stream-level retry spec): three-stage timeouts (first-chunk / idle / hard) sit on top of
  LiteLLM's request-level retries to detect "stream started but stalled" scenarios. Whenever a stream
  ends incomplete (timeout, decode error, or missing finish_reason), we set
  ``LLMStreamResult.incomplete_reason`` and stop iteration — the engine layer decides whether to retry.
  The hard timeout is the only condition we surface as ``LLMAPIError`` directly, since by definition
  no further retry should happen.
"""
import asyncio
import inspect
import json
import logging
import time
from typing import AsyncIterator

import litellm

from app.configs.settings import settings
from app.libs.llm.base import (
    BaseLLMClient,
    LLMAPIError,
    LLMResponse,
    LLMStreamDelta,
    LLMStreamResult,
    extract_cached_tokens_from_usage,
)

logger = logging.getLogger(__name__)

_MAX_LOG_LEN = 2000

# ── Per-channel concurrency limiter ──
# One asyncio.Semaphore per provider channel, sized by settings. Held for the
# whole duration of an in-flight call (the entire stream for stream_chat) so a
# burst of rounds queues on the semaphore instead of stampeding the provider.
# Semaphores are per event loop / worker process; the global cap is
# ``limit × workers × replicas`` (see LLM_CHANNEL_CONCURRENCY docs).
_channel_semaphores: dict[str, asyncio.Semaphore] = {}
_channel_limit_overrides: dict[str, int] | None = None


def _parse_channel_overrides() -> dict[str, int]:
    global _channel_limit_overrides
    if _channel_limit_overrides is None:
        parsed: dict[str, int] = {}
        for item in settings.LLM_CHANNEL_CONCURRENCY_OVERRIDES.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" not in item:
                logger.warning("Ignoring malformed LLM channel override: %r", item)
                continue
            name, _, num = item.partition(":")
            name = name.strip()
            try:
                limit = int(num.strip())
            except ValueError:
                logger.warning("Ignoring non-integer LLM channel override: %r", item)
                continue
            if not name or limit < 0:
                logger.warning("Ignoring invalid LLM channel override: %r", item)
                continue
            # 0 is meaningful: override this channel to unlimited even when the
            # global LLM_CHANNEL_CONCURRENCY is non-zero.
            if name:
                parsed[name] = limit
        _channel_limit_overrides = parsed
    return _channel_limit_overrides


def _channel_limit(channel: str) -> int:
    """Concurrency cap for a channel; 0 means unlimited."""
    override = _parse_channel_overrides().get(channel)
    if override is not None:
        return override
    return settings.LLM_CHANNEL_CONCURRENCY


def _channel_semaphore(channel: str) -> asyncio.Semaphore | None:
    """The channel's limiter, or ``None`` when unlimited (limit <= 0)."""
    limit = _channel_limit(channel)
    if limit <= 0:
        return None
    sem = _channel_semaphores.get(channel)
    if sem is None:
        sem = asyncio.Semaphore(limit)
        _channel_semaphores[channel] = sem
    return sem

# Short name -> LiteLLM model identifier (OpenRouter fallback)
OPENROUTER_MODEL_MAP: dict[str, str] = {
    "deepseek-v4-pro": "openrouter/deepseek/deepseek-v4-pro",
    "deepseek-v4-flash": "openrouter/deepseek/deepseek-v4-flash",
    "kimi-k2.6": "openrouter/moonshotai/kimi-k2.6",
    "glm-5.1": "openrouter/z-ai/glm-5.1",
    "mimo-v2.5-pro": "openrouter/xiaomi/mimo-v2.5-pro",
    "minimax-m2.7": "openrouter/minimax/minimax-m2.7",
}

MODEL_ALIASES: dict[str, str] = {
    "deepseek-v4-pro-official": "deepseek-v4-pro",
}


def _provider_base_urls() -> dict[str, str]:
    # Read at call-site so tests / runtime overrides via env vars take effect.
    from app.configs.settings import settings

    return {
        "openrouter/": settings.OPENROUTER_BASE_URL,
    }


# Compatibility shim: keep the constant name some call-sites import directly.
PROVIDER_BASE_URLS: dict[str, str] = _provider_base_urls()

# Bailian (DashScope compatible-mode) model ids — short UI name -> upstream id.
# Upstream examples: kimi/kimi-k2.6, ZHIPU/GLM-5.1, MiniMax/MiniMax-M2.7
BAILIAN_MODEL_MAP: dict[str, str] = {
    "deepseek-v4-pro": "openai/deepseek-v4-pro",
    "deepseek-v4-flash": "openai/deepseek-v4-flash",
    "kimi-k2.6": "openai/kimi/kimi-k2.6",
    "glm-5.1": "openai/ZHIPU/GLM-5.1",
    "minimax-m2.7": "openai/MiniMax/MiniMax-M2.7",
    # Cheap/fast model used for conversation title summarization.
    "qwen3.6-flash": "openai/qwen3.6-flash",
}

OFFICIAL_MODEL_MAP: dict[str, dict] = {
    "deepseek-v4-pro": {
        "channel": "deepseek-official",
        "model": "openai/deepseek-v4-pro",
        "api_key_setting": "DEEPSEEK_API_KEY",
        "api_base_setting": "DEEPSEEK_API_BASE_URL",
    },
    "deepseek-v4-flash": {
        "channel": "deepseek-official",
        "model": "openai/deepseek-v4-flash",
        "api_key_setting": "DEEPSEEK_API_KEY",
        "api_base_setting": "DEEPSEEK_API_BASE_URL",
    },
    "minimax-m2.7": {
        "channel": "minimax-official",
        "model": "openai/MiniMax-M2.7",
        "api_key_setting": "MINIMAX_API_KEY",
        "api_base_setting": "MINIMAX_BASE_URL",
    },
    "kimi-k2.6": {
        "channel": "moonshot-official",
        "model": "openai/kimi-k2.6",
        "api_key_setting": "MOONSHOT_API_KEY",
        "api_base_setting": "MOONSHOT_BASE_URL",
        "temperature": 1.0,
    },
    "glm-5.1": {
        "channel": "zhipu-official",
        "model": "openai/glm-5.1",
        "api_key_setting": "ZHIPU_API_KEY",
        "api_base_setting": "ZHIPU_BASE_URL",
    },
}

SILICONFLOW_MODEL_MAP: dict[str, str] = {
    "kimi-k2.6": "openai/Pro/moonshotai/Kimi-K2.6",
    "glm-5.1": "openai/Pro/zai-org/GLM-5.1",
}

OFFICIAL_ONLY_MODEL_IDS: frozenset[str] = frozenset()
OFFICIAL_FIRST_MODEL_IDS: frozenset[str] = frozenset(
    {"deepseek-v4-pro", "deepseek-v4-flash"}
)

PROVIDER_CHANNEL_NAMES: dict[str, str] = {
    "aliyun-bailian": "阿里百炼",
    "deepseek-official": "DeepSeek 官方",
    "minimax-official": "MiniMax 官方",
    "moonshot-official": "Kimi 官方",
    "zhipu-official": "智谱官方",
    "siliconflow": "硅基流动",
    "openrouter": "OpenRouter",
}

# OpenAI-compat finish_reason values that mean "the upstream LLM finished by itself".
# Anything else after a stream natural-end is treated as "incomplete" (stream-level retry spec §4.2).
_VALID_FINISH_REASONS: frozenset[str] = frozenset(
    {"stop", "tool_calls", "length", "content_filter"}
)

# Incomplete reasons surfaced to the engine via LLMStreamResult.incomplete_reason.
# Keep them stable — they leak into OTel attributes and audit logs.
INCOMPLETE_CONNECT_TIMEOUT = "stream_connect_timeout"
INCOMPLETE_FIRST_CHUNK_TIMEOUT = "first_chunk_timeout"
INCOMPLETE_IDLE_TIMEOUT = "idle_timeout"
INCOMPLETE_STREAM_ERROR = "stream_error"
INCOMPLETE_MISSING_FINISH = "missing_finish_reason"
INCOMPLETE_HARD_TIMEOUT = "hard_timeout"  # only used in the LLMAPIError message

litellm.drop_params = True
# LiteLLM's aiohttp transport has produced leaked ClientSession warnings in
# production. Use its httpx transport instead; our direct HTTP integrations
# already use httpx with scoped clients.
litellm.disable_aiohttp_transport = True


async def _close_litellm_stream(obj: object) -> None:
    close = getattr(obj, "aclose", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result
        return
    close = getattr(obj, "close", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result


def _merge_extra_body(kwargs: dict, patch: dict) -> None:
    """Merge a dict patch into kwargs['extra_body'] (create if missing)."""
    if not patch:
        return
    extra = kwargs.get("extra_body")
    if extra is None:
        kwargs["extra_body"] = dict(patch)
    elif isinstance(extra, dict):
        kwargs["extra_body"] = {**extra, **patch}


def _drop_extra_body_keys(kwargs: dict, keys: tuple[str, ...]) -> None:
    extra = kwargs.get("extra_body")
    if not isinstance(extra, dict):
        return
    new_extra = {k: v for k, v in extra.items() if k not in keys}
    if new_extra:
        kwargs["extra_body"] = new_extra
    else:
        kwargs.pop("extra_body", None)


def _thinking_off_patch(resolved_model: str) -> dict:
    """Return provider-specific params that TRULY disable reasoning upstream.

    Goal: honor the design intent of "skip thinking to reduce first-token latency"
    — must actually suppress the reasoning phase on the provider, not just hide it.

    Routing:
    - z-ai / GLM        -> `thinking: {"type": "disabled"}` (Z.AI native, passed
                          through by OpenRouter). See: https://docs.z.ai/guides/capabilities/thinking
    - OpenAI o-series /
      GPT-5 / Grok      -> `reasoning: {"effort": "none"}` (OpenRouter spec).
    - Others (MiniMax,
      Claude, Gemini…)  -> `reasoning: {"exclude": true}` as a best-effort
                          fallback: hides reasoning from the response. Note that
                          some proxies/providers still consume reasoning tokens
                          and may perturb tool_calls — this is an upstream
                          limitation documented at the call site.
    """
    m = resolved_model.lower()
    if "/z-ai/" in m or "/glm" in m:
        return {"thinking": {"type": "disabled"}}
    if (
        "/openai/o" in m
        or "/openai/gpt-5" in m
        or "/x-ai/" in m
        or "/grok" in m
    ):
        return {"reasoning": {"effort": "none"}}
    return {"reasoning": {"exclude": True}}


def _apply_openrouter_thinking(kwargs: dict, thinking_enabled: bool, resolved_model: str) -> None:
    """Send provider-specific reasoning params based on the target model.

    On  -> `reasoning: {"effort": "medium"}` (OpenRouter unified enable).
    Off -> provider-specific "true off" (see `_thinking_off_patch`).

    We always strip any pre-existing `reasoning`/`thinking` keys first so
    repeated calls with different settings don't leak state.
    """
    _drop_extra_body_keys(kwargs, ("reasoning", "thinking"))
    if thinking_enabled:
        _merge_extra_body(kwargs, {"reasoning": {"effort": "medium"}})
    else:
        _merge_extra_body(kwargs, _thinking_off_patch(resolved_model))


def _reasoning_details_text(value: object) -> str | None:
    """Flatten OpenRouter `reasoning_details` (list of typed objects) to plain text."""
    if not isinstance(value, list) or not value:
        return None
    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        typ = item.get("type")
        if typ == "reasoning.text":
            t = item.get("text")
            if isinstance(t, str) and t.strip():
                parts.append(t.strip())
        elif typ == "reasoning.summary":
            s = item.get("summary")
            if isinstance(s, str) and s.strip():
                parts.append(s.strip())
    if not parts:
        return None
    return "\n".join(parts)


def _strip_leading_orphan_think_close(text: object) -> str | None:
    """Drop provider-leaked leading ``</think>`` control tags from visible text."""
    if not isinstance(text, str):
        return None

    cleaned = text
    while True:
        stripped = cleaned.lstrip()
        if not stripped.lower().startswith("</think>"):
            return cleaned
        cleaned = stripped[len("</think>"):].lstrip()
        if not cleaned:
            return None


def _message_thinking_text(msg: object) -> str | None:
    """Collect reasoning/thinking from provider-specific message fields."""
    for attr in ("thinking_content", "reasoning_content", "reasoning"):
        v = getattr(msg, attr, None)
        v = _strip_leading_orphan_think_close(v)
        if v and v.strip():
            return v
    rd = _reasoning_details_text(getattr(msg, "reasoning_details", None))
    if rd:
        return rd
    return None


def _delta_thinking_text(delta: object) -> str | None:
    for attr in ("thinking_content", "reasoning_content", "reasoning"):
        v = getattr(delta, attr, None)
        v = _strip_leading_orphan_think_close(v)
        if v:
            return v
    rd = _reasoning_details_text(getattr(delta, "reasoning_details", None))
    if rd:
        return rd
    return None


def _truncate(obj: object, max_len: int = _MAX_LOG_LEN) -> str:
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if len(text) > max_len:
        return text[:max_len] + f"...(truncated, total {len(text)} chars)"
    return text


def _resolve_model(model: str) -> str:
    """Map a short model name to a LiteLLM model identifier."""
    return OPENROUTER_MODEL_MAP.get(model, model)


def _is_bailian_deepseek_v4_model(channel: str, resolved_model: str) -> bool:
    return channel == "aliyun-bailian" and resolved_model in {
        "openai/deepseek-v4-pro",
        "openai/deepseek-v4-flash",
    }


def _preserve_reasoning_content(channel: str, resolved_model: str) -> bool:
    """Whether historical assistant reasoning should be replayed upstream."""
    if channel == "deepseek-official":
        return True
    if _is_bailian_deepseek_v4_model(channel, resolved_model):
        return True
    m = resolved_model.lower()
    return "kimi" in m or "moonshot" in m


def _messages_for_channel(messages: list[dict], channel: str, resolved_model: str) -> list[dict]:
    """Return request messages adjusted for provider-specific extensions."""
    if _preserve_reasoning_content(channel, resolved_model):
        return messages

    changed = False
    sanitized: list[dict] = []
    for message in messages:
        if "reasoning_content" not in message:
            sanitized.append(message)
            continue
        item = dict(message)
        item.pop("reasoning_content", None)
        sanitized.append(item)
        changed = True
    return sanitized if changed else messages


def _provider_base(resolved: str) -> dict:
    """Return api_base kwarg if the resolved model matches a known provider prefix.

    Reads from settings on each call so OPENROUTER_BASE_URL overrides via env
    take effect at runtime (and in tests).
    """
    for prefix, base_url in _provider_base_urls().items():
        if resolved.startswith(prefix):
            return {"api_base": base_url}
    return {}


def _parse_provider_channels(raw: str) -> list[str] | None:
    """Parse ``LLM_PROVIDER_CHANNELS`` into an ordered allowlist, or None if unset."""
    text = (raw or "").strip()
    if not text:
        return None
    channels: list[str] = []
    for part in text.split(","):
        ch = part.strip()
        if ch and ch not in channels:
            channels.append(ch)
    return channels or None


def _bailian_candidate(model: str, *, allow_unmapped: bool = False) -> dict | None:
    if model in OFFICIAL_ONLY_MODEL_IDS:
        return None
    if not settings.ALIYUN_BAILIAN_API_KEY:
        return None
    bailian_model = BAILIAN_MODEL_MAP.get(model)
    if not bailian_model:
        if not allow_unmapped:
            return None
        bailian_model = f"openai/{model}"
    return {
        "channel": "aliyun-bailian",
        "model": bailian_model,
        "api_key": settings.ALIYUN_BAILIAN_API_KEY,
        "api_base": settings.ALIYUN_BAILIAN_BASE_URL,
    }


def _official_candidate(model: str) -> dict | None:
    official = OFFICIAL_MODEL_MAP.get(model)
    if not official:
        return None
    api_key = getattr(settings, official["api_key_setting"])
    if not api_key:
        return None
    return {
        "channel": official["channel"],
        "model": official["model"],
        "api_key": api_key,
        "api_base": getattr(settings, official["api_base_setting"]),
        **(
            {"temperature": official["temperature"]}
            if "temperature" in official
            else {}
        ),
    }


def _filter_candidates_by_channels(
    candidates: list[dict], allowed: list[str], model: str
) -> list[dict]:
    """Keep only allowed channels, preserving the env-configured order."""
    by_channel: dict[str, dict] = {}
    for candidate in candidates:
        by_channel.setdefault(candidate["channel"], candidate)

    filtered: list[dict] = []
    for channel in allowed:
        if channel in by_channel:
            filtered.append(by_channel[channel])
        elif channel == "aliyun-bailian":
            extra = _bailian_candidate(model, allow_unmapped=True)
            if extra:
                filtered.append(extra)
    return filtered


def _model_candidates(model: str) -> list[dict]:
    """Return provider candidates in priority order for a user-selected model."""
    model = MODEL_ALIASES.get(model, model)
    candidates: list[dict] = []

    if model in OFFICIAL_FIRST_MODEL_IDS:
        official = _official_candidate(model)
        if official:
            candidates.append(official)

    bailian = _bailian_candidate(model)
    if bailian:
        candidates.append(bailian)

    if model not in OFFICIAL_FIRST_MODEL_IDS:
        official = _official_candidate(model)
        if official:
            candidates.append(official)

    siliconflow_model = SILICONFLOW_MODEL_MAP.get(model)
    if siliconflow_model and settings.SILICONFLOW_API_KEY:
        candidates.append(
            {
                "channel": "siliconflow",
                "model": siliconflow_model,
                "api_key": settings.SILICONFLOW_API_KEY,
                "api_base": settings.SILICONFLOW_BASE_URL,
            }
        )

    resolved = _resolve_model(model)
    candidates.append(
        {
            "channel": "openrouter",
            "model": resolved,
            "api_key": settings.OPENROUTER_API_KEY,
            **_provider_base(resolved),
        }
    )

    allowed = _parse_provider_channels(settings.LLM_PROVIDER_CHANNELS)
    if allowed:
        return _filter_candidates_by_channels(candidates, allowed, model)
    return candidates


def _log_provider_fallback(
    *, model: str, from_channel: str, to_channel: str, reason: str, mode: str,
    detail: str = "",
) -> None:
    """Structured WARN log for a provider-channel fallback (degradation).

    Emits a stable body phrase ("LLM provider fallback") plus flat
    ``log_attributes`` fields so downstream log aggregation (e.g. the daily
    report) can count fallbacks per model without parsing free text.
    """
    logger.warning(
        "LLM provider fallback — model=%s, from=%s, to=%s, reason=%s, mode=%s%s",
        model, from_channel, to_channel, reason, mode,
        f", detail={detail[:_MAX_LOG_LEN]}" if detail else "",
        extra={
            "llm_provider_fallback": "1",
            "fallback_model": model,
            "fallback_from": from_channel,
            "fallback_to": to_channel,
            "fallback_reason": reason,
            "fallback_mode": mode,
        },
    )


def _reliability_kwargs() -> dict:
    """LiteLLM kwargs for retries / timeout (env-driven)."""
    out: dict = {"num_retries": settings.LLM_NUM_RETRIES}
    if settings.LLM_REQUEST_TIMEOUT_SEC is not None:
        out["timeout"] = settings.LLM_REQUEST_TIMEOUT_SEC
    return out


def _apply_thinking(kwargs: dict, thinking_enabled: bool, resolved_model: str, channel: str) -> None:
    """Apply provider-specific reasoning params."""
    if channel == "openrouter":
        _apply_openrouter_thinking(kwargs, thinking_enabled, resolved_model)
    elif channel == "deepseek-official":
        _merge_extra_body(
            kwargs,
            {"thinking": {"type": "enabled" if thinking_enabled else "disabled"}},
        )
        if thinking_enabled:
            kwargs["reasoning_effort"] = "high"
    elif _is_bailian_deepseek_v4_model(channel, resolved_model):
        _merge_extra_body(kwargs, {"enable_thinking": thinking_enabled})
        if thinking_enabled:
            kwargs["reasoning_effort"] = "high"
    elif channel == "aliyun-bailian" and "qwen" in resolved_model.lower():
        # Qwen3 models on DashScope default to thinking ON, which burns ~1k
        # reasoning tokens even for a few-char output (e.g. the conversation
        # title summary). Honor the caller's flag explicitly so thinking-off
        # paths actually disable it.
        _merge_extra_body(kwargs, {"enable_thinking": thinking_enabled})
    elif channel == "minimax-official" and thinking_enabled:
        _merge_extra_body(kwargs, {"reasoning_split": True})


def _request_kwargs(
    candidate: dict,
    *,
    messages: list[dict],
    temperature: float,
    top_p: float,
    max_tokens: int,
    stream: bool,
) -> dict:
    """Build common LiteLLM request kwargs for one provider candidate."""
    kwargs: dict = {
        "model": candidate["model"],
        "messages": _messages_for_channel(messages, candidate["channel"], candidate["model"]),
        "temperature": candidate.get("temperature", temperature),
        "top_p": top_p,
        "max_tokens": max_tokens,
        "api_key": candidate["api_key"],
        "stream": stream,
        **_reliability_kwargs(),
    }
    if candidate.get("api_base"):
        kwargs["api_base"] = candidate["api_base"]
    if stream:
        kwargs["stream_options"] = {"include_usage": True}
    return kwargs


class LiteLLMClient(BaseLLMClient):
    """LLM client powered by LiteLLM, routing through OpenRouter."""

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.01,
        top_p: float = 0.85,
        max_tokens: int = 4096,
        thinking_enabled: bool = False,
    ) -> LLMResponse:
        candidates = _model_candidates(model)
        response = None
        selected_channel = ""
        for idx, candidate in enumerate(candidates):
            resolved = candidate["model"]
            channel = candidate["channel"]
            kwargs = _request_kwargs(
                candidate,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stream=False,
            )
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            _apply_thinking(kwargs, thinking_enabled, resolved, channel)

            logger.info(
                "LLM request (sync) — model=%s(%s), channel=%s, messages=%d, tools=%s, thinking=%s",
                model, resolved, channel, len(messages), len(tools) if tools else 0, thinking_enabled,
            )

            sem = _channel_semaphore(channel)
            if sem is not None:
                await sem.acquire()
            try:
                response = await litellm.acompletion(**kwargs)
                selected_channel = channel
                break
            except litellm.exceptions.APIError as exc:
                if idx < len(candidates) - 1:
                    _log_provider_fallback(
                        model=model, from_channel=channel,
                        to_channel=candidates[idx + 1]["channel"],
                        reason="api_error", mode="sync", detail=str(exc),
                    )
                    continue
                logger.error("LiteLLM API error — %s", exc)
                raise LLMAPIError(
                    status_code=getattr(exc, "status_code", 500),
                    message=str(exc),
                ) from exc
            finally:
                # Sync call: the provider work is done once acompletion returns,
                # so always release (no streaming hold like stream_chat).
                if sem is not None:
                    sem.release()

        if response is None:
            raise LLMAPIError(status_code=500, message="LLM request failed without response")

        choice = response.choices[0]
        msg = choice.message
        usage = response.usage or litellm.Usage()

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]

        # If the caller disabled thinking, drop any reasoning returned by the
        # upstream model so it is neither shown in the UI nor persisted.
        thinking_text = _message_thinking_text(msg) if thinking_enabled else None

        result = LLMResponse(
            content=_strip_leading_orphan_think_close(msg.content),
            thinking_content=thinking_text,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            cached_tokens=extract_cached_tokens_from_usage(usage),
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
            request_id=response.id,
            model=response.model,
            provider_channel=selected_channel or None,
            provider_name=PROVIDER_CHANNEL_NAMES.get(selected_channel),
        )

        logger.info(
            "LLM response (sync) — model=%s, finish=%s, tokens(in=%s/cached=%s/out=%s/total=%s)",
            result.model, result.finish_reason,
            result.input_tokens, result.cached_tokens, result.output_tokens, result.total_tokens,
        )
        return result

    async def stream_chat(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.01,
        top_p: float = 0.85,
        max_tokens: int = 4096,
        thinking_enabled: bool = False,
    ) -> tuple[AsyncIterator[LLMStreamDelta], LLMStreamResult]:
        candidates = _model_candidates(model)
        result = LLMStreamResult()

        async def _stream() -> AsyncIterator[LLMStreamDelta]:
            response = None
            held_sem: asyncio.Semaphore | None = None
            for idx, candidate in enumerate(candidates):
                resolved = candidate["model"]
                channel = candidate["channel"]
                kwargs = _request_kwargs(
                    candidate,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    stream=True,
                )
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                _apply_thinking(kwargs, thinking_enabled, resolved, channel)

                logger.info(
                    "LLM request (stream) — model=%s(%s), channel=%s, messages=%d, tools=%s, thinking=%s",
                    model, resolved, channel, len(messages), len(tools) if tools else 0, thinking_enabled,
                )

                # Gate on the channel limiter BEFORE opening the upstream stream,
                # so a queued call doesn't hold a provider connection while it
                # waits. Released on failover/failure here; on success it is held
                # by ``held_sem`` and freed in the streaming ``finally`` below.
                sem = _channel_semaphore(channel)
                if sem is not None:
                    await sem.acquire()
                selected = False
                try:
                    response = await asyncio.wait_for(
                        litellm.acompletion(**kwargs),
                        timeout=settings.LLM_FIRST_CHUNK_TIMEOUT_SEC,
                    )
                    selected = True
                except asyncio.TimeoutError:
                    if idx < len(candidates) - 1:
                        _log_provider_fallback(
                            model=model, from_channel=channel,
                            to_channel=candidates[idx + 1]["channel"],
                            reason="connect_timeout", mode="stream",
                        )
                        continue
                    logger.warning(
                        "LLM stream incomplete — reason=%s, model=%s, channel=%s",
                        INCOMPLETE_CONNECT_TIMEOUT,
                        model,
                        channel,
                    )
                    result.incomplete_reason = INCOMPLETE_CONNECT_TIMEOUT
                    return
                except (asyncio.CancelledError, GeneratorExit):
                    raise
                except litellm.exceptions.APIError as exc:
                    if idx < len(candidates) - 1:
                        _log_provider_fallback(
                            model=model, from_channel=channel,
                            to_channel=candidates[idx + 1]["channel"],
                            reason="api_error", mode="stream", detail=str(exc),
                        )
                        continue
                    logger.error("LiteLLM API error — %s", exc)
                    raise LLMAPIError(
                        status_code=getattr(exc, "status_code", 500),
                        message=str(exc),
                    ) from exc
                finally:
                    if sem is not None and not selected:
                        sem.release()

                result.provider_channel = channel
                result.provider_name = PROVIDER_CHANNEL_NAMES.get(channel)
                held_sem = sem
                break

            if response is None:
                raise LLMAPIError(status_code=500, message="LLM request failed without response")

            # ── Three-stage timeouts (stream-level retry spec) ──
            # We need per-chunk timeouts (first-chunk vs idle gap) AND a wall-clock
            # cap on the whole stream. Driving the iterator manually with
            # ``asyncio.wait_for(__anext__(...))`` is the only way to express that
            # without relying on a fragile ``asyncio.timeout`` wrapper around the
            # whole `async for` (which can't distinguish first-chunk from idle).
            first_chunk_timeout = settings.LLM_FIRST_CHUNK_TIMEOUT_SEC
            idle_timeout = settings.LLM_IDLE_TIMEOUT_SEC
            hard_timeout = settings.LLM_HARD_TIMEOUT_SEC
            stream_started_at = time.monotonic()
            has_first_chunk = False
            chunk_iter = response.__aiter__()

            try:
                while True:
                    # Hard wall-clock check — never retry past this point.
                    elapsed = time.monotonic() - stream_started_at
                    if elapsed > hard_timeout:
                        logger.warning(
                            "LLM stream hard timeout — model=%s, elapsed=%.1fs > limit=%.1fs",
                            result.model or model, elapsed, hard_timeout,
                        )
                        raise LLMAPIError(
                            status_code=504,
                            message=f"LLM stream hard timeout after {elapsed:.1f}s",
                            error_type=INCOMPLETE_HARD_TIMEOUT,
                        )

                    # Choose per-step timeout: first-chunk vs idle gap.
                    # Cap by remaining hard-timeout budget so a slow first chunk can't
                    # silently push us past the wall-clock limit.
                    step_timeout = first_chunk_timeout if not has_first_chunk else idle_timeout
                    step_timeout = min(step_timeout, max(hard_timeout - elapsed, 0.1))

                    try:
                        chunk = await asyncio.wait_for(
                            chunk_iter.__anext__(), timeout=step_timeout
                        )
                    except StopAsyncIteration:
                        # Natural end-of-stream — break and validate finish_reason below.
                        break
                    except asyncio.TimeoutError:
                        reason = (
                            INCOMPLETE_FIRST_CHUNK_TIMEOUT
                            if not has_first_chunk
                            else INCOMPLETE_IDLE_TIMEOUT
                        )
                        logger.warning(
                            "LLM stream incomplete — reason=%s, model=%s, partial_chars=%d, "
                            "thinking_chars=%d, elapsed=%.1fs, step_timeout=%.1fs",
                            reason, result.model or model, len(result.content),
                            len(result.thinking_content), elapsed, step_timeout,
                        )
                        result.incomplete_reason = reason
                        return
                    except (asyncio.CancelledError, GeneratorExit):
                        # Client disconnect / engine cancellation — propagate verbatim
                        # so engine retry logic sees CancelledError and bails out.
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "LLM stream error mid-stream — reason=%s, model=%s, exc=%s",
                            INCOMPLETE_STREAM_ERROR, result.model or model, exc,
                        )
                        result.incomplete_reason = INCOMPLETE_STREAM_ERROR
                        return

                    has_first_chunk = True

                    if chunk.id:
                        result.request_id = chunk.id
                    if chunk.model:
                        result.model = chunk.model

                    usage = getattr(chunk, "usage", None)
                    if usage:
                        result.input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                        result.cached_tokens = extract_cached_tokens_from_usage(usage)
                        result.output_tokens = getattr(usage, "completion_tokens", 0) or 0
                        result.total_tokens = getattr(usage, "total_tokens", 0) or 0

                    choices = chunk.choices
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.delta
                    finish_reason = choice.finish_reason

                    content = _strip_leading_orphan_think_close(getattr(delta, "content", None))
                    # Drop reasoning locally when thinking is disabled — avoids
                    # passing OpenRouter reasoning suppression flags that are
                    # interpreted inconsistently and can break tool_calls.
                    thinking = _delta_thinking_text(delta) if thinking_enabled else None
                    raw_tool_calls = getattr(delta, "tool_calls", None)

                    if content:
                        result.content += content
                    if thinking:
                        result.thinking_content += thinking
                    if finish_reason:
                        result.finish_reason = finish_reason

                    tool_calls_dicts = None
                    if raw_tool_calls:
                        tool_calls_dicts = []
                        for tc in raw_tool_calls:
                            idx = getattr(tc, "index", 0) or 0
                            while len(result.tool_calls) <= idx:
                                result.tool_calls.append(
                                    {
                                        "id": "",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                )
                            existing = result.tool_calls[idx]
                            tc_id = getattr(tc, "id", None)
                            if tc_id:
                                existing["id"] = tc_id
                            fn = getattr(tc, "function", None)
                            if fn:
                                name = getattr(fn, "name", None)
                                args = getattr(fn, "arguments", None)
                                if name:
                                    existing["function"]["name"] += name
                                if args:
                                    existing["function"]["arguments"] += args

                            tool_calls_dicts.append(
                                {
                                    "index": idx,
                                    "id": tc_id or "",
                                    "function": {
                                        "name": getattr(fn, "name", "") or "",
                                        "arguments": getattr(fn, "arguments", "") or "",
                                    },
                                }
                            )

                    yield LLMStreamDelta(
                        content=content,
                        thinking_content=thinking,
                        tool_calls=tool_calls_dicts,
                        finish_reason=finish_reason,
                    )
            finally:
                await _close_litellm_stream(chunk_iter)
                if chunk_iter is not response:
                    await _close_litellm_stream(response)
                if held_sem is not None:
                    held_sem.release()

            # ── Stream finished naturally — validate finish_reason ──
            # `length` counts as "valid" here (engine-level continuation is out of
            # scope for this feature, see stream-level retry spec §4.2 note).
            if result.finish_reason not in _VALID_FINISH_REASONS:
                logger.warning(
                    "LLM stream incomplete — reason=%s, model=%s, finish=%r, partial_chars=%d",
                    INCOMPLETE_MISSING_FINISH, result.model or model,
                    result.finish_reason, len(result.content),
                )
                result.incomplete_reason = INCOMPLETE_MISSING_FINISH
                return

            logger.info(
                "LLM stream done — request_id=%s, model=%s, finish=%s, "
                "tokens(in=%s/out=%s/total=%s), tool_calls=%d, content_len=%d",
                result.request_id,
                result.model,
                result.finish_reason,
                result.input_tokens,
                result.output_tokens,
                result.total_tokens,
                len(result.tool_calls),
                len(result.content),
            )

        return _stream(), result
