"""
OpenAI-compatible LLM provider — works with OpenAI, DeepSeek, Qwen, and other
providers exposing an OpenAI-style Chat Completions API.
"""
import json
import logging
from typing import AsyncIterator

import httpx

from app.configs.settings import settings
from app.libs.llm.base import BaseLLMClient, LLMAPIError, LLMResponse, LLMStreamDelta, LLMStreamResult

logger = logging.getLogger(__name__)

_MAX_LOG_LEN = 2000


def _truncate(obj: object, max_len: int = _MAX_LOG_LEN) -> str:
    """JSON-serialize and truncate for logging."""
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if len(text) > max_len:
        return text[:max_len] + f"...(truncated, total {len(text)} chars)"
    return text


class OpenAICompatibleClient(BaseLLMClient):

    def __init__(self) -> None:
        self._api_key = settings.LLM_API_KEY
        self._base_url = settings.LLM_BASE_URL.rstrip("/")

    def _build_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_body(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.01,
        top_p: float = 0.85,
        max_tokens: int = 4096,
        thinking_enabled: bool = False,
        stream: bool = False,
    ) -> dict:
        body: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    def _log_request(self, mode: str, url: str, body: dict) -> None:
        body_summary = {k: v for k, v in body.items() if k != "messages"}
        body_summary["messages_count"] = len(body.get("messages", []))
        logger.info("LLM request (%s) — url=%s, params=%s", mode, url, _truncate(body_summary))
        logger.info(
            "LLM request (%s) — full body:\n%s",
            mode, json.dumps(body, ensure_ascii=False, indent=2, default=str),
        )

    def _log_response(self, mode: str, data: dict) -> None:
        logger.info("LLM response (%s) — %s", mode, _truncate(data))

    def _log_error(self, mode: str, resp: httpx.Response) -> None:
        try:
            error_body = resp.text
        except Exception:
            error_body = "<unreadable>"
        logger.error(
            "LLM error (%s) — status=%s, url=%s, response_body=%s",
            mode, resp.status_code, resp.url, error_body,
        )

    @staticmethod
    def _raise_api_error(resp: httpx.Response) -> None:
        """Parse the API error body and raise LLMAPIError with details."""
        try:
            body = json.loads(resp.text)
            err = body.get("error", {})
            message = err.get("message", resp.text)
            param = err.get("param")
            error_type = err.get("type")
        except Exception:
            message = resp.text or f"HTTP {resp.status_code}"
            param = None
            error_type = None
        raise LLMAPIError(
            status_code=resp.status_code,
            message=message,
            param=param,
            error_type=error_type,
        )

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
        body = self._build_body(
            messages, model=model, tools=tools,
            temperature=temperature, top_p=top_p,
            max_tokens=max_tokens, thinking_enabled=thinking_enabled,
            stream=False,
        )
        url = f"{self._base_url}/chat/completions"
        self._log_request("sync", url, body)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=self._build_headers(), json=body)
            if resp.status_code != 200:
                self._log_error("sync", resp)
                self._raise_api_error(resp)
            data = resp.json()

        self._log_response("sync", data)

        choice = data["choices"][0]
        msg = choice["message"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=msg.get("content"),
            thinking_content=msg.get("thinking_content") or msg.get("reasoning_content"),
            tool_calls=msg.get("tool_calls"),
            finish_reason=choice.get("finish_reason"),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            request_id=data.get("id"),
            model=data.get("model"),
        )

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
        body = self._build_body(
            messages, model=model, tools=tools,
            temperature=temperature, top_p=top_p,
            max_tokens=max_tokens, thinking_enabled=thinking_enabled,
            stream=True,
        )
        result = LLMStreamResult()
        url = f"{self._base_url}/chat/completions"
        self._log_request("stream", url, body)

        async def _stream() -> AsyncIterator[LLMStreamDelta]:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", url,
                    headers=self._build_headers(),
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        await resp.aread()
                        self._log_error("stream", resp)
                        self._raise_api_error(resp)
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        if chunk.get("id"):
                            result.request_id = chunk["id"]
                        if chunk.get("model"):
                            result.model = chunk["model"]

                        usage = chunk.get("usage")
                        if usage:
                            result.input_tokens = usage.get("prompt_tokens", 0)
                            result.output_tokens = usage.get("completion_tokens", 0)
                            result.total_tokens = usage.get("total_tokens", 0)

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue

                        choice = choices[0]
                        delta = choice.get("delta", {})
                        finish_reason = choice.get("finish_reason")

                        content = delta.get("content")
                        thinking = delta.get("thinking_content") or delta.get("reasoning_content")
                        tool_calls = delta.get("tool_calls")

                        if content:
                            result.content += content
                        if thinking:
                            result.thinking_content += thinking
                        if finish_reason:
                            result.finish_reason = finish_reason

                        # Accumulate tool_calls from deltas
                        if tool_calls:
                            for tc in tool_calls:
                                idx = tc.get("index", 0)
                                while len(result.tool_calls) <= idx:
                                    result.tool_calls.append({
                                        "id": "", "type": "function",
                                        "function": {"name": "", "arguments": ""}
                                    })
                                existing = result.tool_calls[idx]
                                if tc.get("id"):
                                    existing["id"] = tc["id"]
                                fn = tc.get("function", {})
                                if fn.get("name"):
                                    existing["function"]["name"] += fn["name"]
                                if fn.get("arguments"):
                                    existing["function"]["arguments"] += fn["arguments"]

                        stream_delta = LLMStreamDelta(
                            content=content,
                            thinking_content=thinking,
                            tool_calls=tool_calls,
                            finish_reason=finish_reason,
                        )
                        yield stream_delta

            logger.info(
                "LLM stream done — request_id=%s, model=%s, finish=%s, "
                "tokens(in=%s/out=%s/total=%s), tool_calls=%d, content_len=%d",
                result.request_id, result.model, result.finish_reason,
                result.input_tokens, result.output_tokens, result.total_tokens,
                len(result.tool_calls), len(result.content),
            )

        return _stream(), result
