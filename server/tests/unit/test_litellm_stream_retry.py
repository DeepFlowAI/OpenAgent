"""
Unit tests for stream-level reliability detection inside ``LiteLLMClient.stream_chat``
(see the stream-level retry spec).

These tests stub out ``litellm.acompletion`` with fake async-iterable streams so
nothing leaves the process — no real OpenRouter / MiniMax calls happen, no tokens
spent. We verify that:
    - Slow stream connection sets ``incomplete_reason='stream_connect_timeout'``.
    - First-chunk timeout sets ``incomplete_reason='first_chunk_timeout'``.
    - Idle gap timeout sets ``incomplete_reason='idle_timeout'``.
    - Mid-stream exception sets ``incomplete_reason='stream_error'``.
    - Missing/unknown ``finish_reason`` sets ``incomplete_reason='missing_finish_reason'``.
    - Hard wall-clock timeout raises ``LLMAPIError`` (no incomplete_reason path).
    - A clean stream leaves ``incomplete_reason`` as ``None``.
    - ``CancelledError`` propagates through (engine layer must see it for client-disconnect bailout).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.libs.llm.base import LLMAPIError
from app.libs.llm.providers import litellm_client


# ── Test doubles ──────────────────────────────────────────────────────


def _chunk(
    content: str | None = None,
    finish_reason: str | None = None,
    *,
    tool_calls: list | None = None,
    thinking_content: str | None = None,
    reasoning_content: str | None = None,
    reasoning: str | None = None,
):
    """Build a minimal LiteLLM-shaped SSE chunk."""
    return SimpleNamespace(
        id="resp-id",
        model="MiniMax-M2.7",
        usage=None,
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                delta=SimpleNamespace(
                    content=content,
                    tool_calls=tool_calls,
                    reasoning_details=None,
                    thinking_content=thinking_content,
                    reasoning_content=reasoning_content,
                    reasoning=reasoning,
                ),
            )
        ],
    )


class _ScriptedStream:
    """Async iterator that emits chunks per a script.

    Each script entry can be:
        - a dict ``{"chunk": <chunk>, "delay": <seconds>}`` — sleep then yield
        - the literal ``"raise"`` — raise ``RuntimeError("upstream boom")``
    """

    def __init__(self, script: list):
        self._script = list(script)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._script:
            raise StopAsyncIteration
        item = self._script.pop(0)
        if item == "raise":
            raise RuntimeError("upstream boom")
        delay = item.get("delay", 0)
        if delay:
            await asyncio.sleep(delay)
        return item["chunk"]


class _ClosableScriptedStream(_ScriptedStream):
    def __init__(self, script: list):
        super().__init__(script)
        self.closed = False

    async def aclose(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _stream_test_settings(monkeypatch):
    """Tighten timeouts so tests run in well under a second each.

    These knobs DON'T need to mirror production defaults — we just need them
    short enough to exercise the timeout branches deterministically.
    """
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "key")
    monkeypatch.setattr(litellm_client.settings, "MINIMAX_API_KEY", "")
    monkeypatch.setattr(litellm_client.settings, "LLM_FIRST_CHUNK_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(litellm_client.settings, "LLM_IDLE_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(litellm_client.settings, "LLM_HARD_TIMEOUT_SEC", 5.0)


async def _run(stream_or_factory):
    """Helper: drive ``stream_chat`` with a stubbed acompletion and return result."""
    if callable(stream_or_factory):
        async def fake_acompletion(**kwargs):
            return stream_or_factory()
    else:
        async def fake_acompletion(**kwargs):
            return stream_or_factory

    return fake_acompletion


# ── Tests ─────────────────────────────────────────────────────────────


def test_litellm_aiohttp_transport_is_disabled():
    assert litellm_client.litellm.disable_aiohttp_transport is True


@pytest.mark.asyncio
async def test_stream_connect_timeout_sets_reason(monkeypatch):
    async def fake_acompletion(**kwargs):
        await asyncio.sleep(0.2)
        return _ScriptedStream([
            {"chunk": _chunk(content="late", finish_reason="stop")},
        ])

    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    deltas = [d async for d in stream]

    assert deltas == []
    assert result.incomplete_reason == litellm_client.INCOMPLETE_CONNECT_TIMEOUT
    assert result.content == ""


@pytest.mark.asyncio
async def test_clean_stream_has_no_incomplete_reason(monkeypatch):
    fake_acompletion = await _run(
        _ScriptedStream([
            {"chunk": _chunk(content="hello ")},
            {"chunk": _chunk(content="world", finish_reason="stop")},
        ])
    )
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    deltas = [d async for d in stream]

    assert [d.content for d in deltas if d.content] == ["hello ", "world"]
    assert result.incomplete_reason is None
    assert result.finish_reason == "stop"
    assert result.content == "hello world"


@pytest.mark.asyncio
async def test_orphan_think_close_content_is_dropped_before_tool_call(monkeypatch):
    tool_call = SimpleNamespace(
        index=0,
        id="call_1",
        function=SimpleNamespace(
            name="knowledge_search",
            arguments='{"query":"ECE R13"}',
        ),
    )
    fake_acompletion = await _run(
        _ScriptedStream([
            {
                "chunk": _chunk(
                    content="</think>",
                    tool_calls=[tool_call],
                    finish_reason="tool_calls",
                )
            },
        ])
    )
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    deltas = [d async for d in stream]

    assert [d.content for d in deltas] == [None]
    assert result.content == ""
    assert result.finish_reason == "tool_calls"
    assert result.tool_calls == [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "knowledge_search",
                "arguments": '{"query":"ECE R13"}',
            },
        }
    ]


@pytest.mark.asyncio
async def test_orphan_think_close_prefix_is_stripped_from_visible_content(monkeypatch):
    fake_acompletion = await _run(
        _ScriptedStream([
            {"chunk": _chunk(content="</think>visible", finish_reason="stop")},
        ])
    )
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    deltas = [d async for d in stream]

    assert [d.content for d in deltas if d.content] == ["visible"]
    assert result.content == "visible"


@pytest.mark.asyncio
async def test_first_chunk_timeout_sets_reason(monkeypatch):
    # Delay first chunk longer than first-chunk timeout
    fake_acompletion = await _run(
        _ScriptedStream([
            {"chunk": _chunk(content="late", finish_reason="stop"), "delay": 0.2},
        ])
    )
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    deltas = [d async for d in stream]

    assert deltas == []  # no chunks consumed
    assert result.incomplete_reason == litellm_client.INCOMPLETE_FIRST_CHUNK_TIMEOUT
    assert result.content == ""


@pytest.mark.asyncio
async def test_first_chunk_timeout_closes_stream(monkeypatch):
    upstream = _ClosableScriptedStream([
        {"chunk": _chunk(content="late", finish_reason="stop"), "delay": 0.2},
    ])
    fake_acompletion = await _run(upstream)
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    deltas = [d async for d in stream]

    assert deltas == []
    assert result.incomplete_reason == litellm_client.INCOMPLETE_FIRST_CHUNK_TIMEOUT
    assert upstream.closed is True


@pytest.mark.asyncio
async def test_idle_timeout_after_first_chunk(monkeypatch):
    # First chunk arrives fast, but the next chunk stalls past the idle timeout.
    fake_acompletion = await _run(
        _ScriptedStream([
            {"chunk": _chunk(content="hi")},
            {"chunk": _chunk(content="!", finish_reason="stop"), "delay": 0.2},
        ])
    )
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    deltas = [d async for d in stream]

    assert [d.content for d in deltas if d.content] == ["hi"]
    assert result.incomplete_reason == litellm_client.INCOMPLETE_IDLE_TIMEOUT
    # Partial content is preserved so engine can decide based on chars-shown.
    assert result.content == "hi"


@pytest.mark.asyncio
async def test_mid_stream_exception_marks_stream_error(monkeypatch):
    fake_acompletion = await _run(
        _ScriptedStream([
            {"chunk": _chunk(content="ok")},
            "raise",
        ])
    )
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    deltas = [d async for d in stream]

    assert [d.content for d in deltas if d.content] == ["ok"]
    assert result.incomplete_reason == litellm_client.INCOMPLETE_STREAM_ERROR
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_missing_finish_reason_marks_incomplete(monkeypatch):
    # Stream ends naturally but never sets a valid finish_reason.
    fake_acompletion = await _run(
        _ScriptedStream([
            {"chunk": _chunk(content="hello")},
            {"chunk": _chunk(content=" world")},  # no finish_reason on last chunk
        ])
    )
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    deltas = [d async for d in stream]

    assert [d.content for d in deltas if d.content] == ["hello", " world"]
    assert result.incomplete_reason == litellm_client.INCOMPLETE_MISSING_FINISH
    assert result.finish_reason is None


@pytest.mark.asyncio
async def test_unknown_finish_reason_marks_incomplete(monkeypatch):
    """An out-of-spec finish_reason like "" or "error" should also flag incomplete."""
    fake_acompletion = await _run(
        _ScriptedStream([
            {"chunk": _chunk(content="hi", finish_reason="error")},
        ])
    )
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    _ = [d async for d in stream]

    assert result.incomplete_reason == litellm_client.INCOMPLETE_MISSING_FINISH


@pytest.mark.asyncio
async def test_hard_timeout_raises(monkeypatch):
    """Streams that exceed the wall-clock cap raise LLMAPIError outright."""
    monkeypatch.setattr(litellm_client.settings, "LLM_HARD_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(litellm_client.settings, "LLM_FIRST_CHUNK_TIMEOUT_SEC", 1.0)
    monkeypatch.setattr(litellm_client.settings, "LLM_IDLE_TIMEOUT_SEC", 1.0)

    # Sleep > hard_timeout before first chunk; min(step_timeout, hard_remaining)
    # will let us hit the hard-timeout branch on the second loop iteration.
    fake_acompletion = await _run(
        _ScriptedStream([
            {"chunk": _chunk(content="hi"), "delay": 0.08},
            {"chunk": _chunk(content="!", finish_reason="stop"), "delay": 0.08},
        ])
    )
    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    with pytest.raises(LLMAPIError) as exc_info:
        _ = [d async for d in stream]

    assert exc_info.value.status_code == 504
    assert exc_info.value.error_type == litellm_client.INCOMPLETE_HARD_TIMEOUT
    # `result.incomplete_reason` deliberately stays None — hard_timeout is the
    # one branch that surfaces as exception (engine MUST NOT retry).
    assert result.incomplete_reason is None


@pytest.mark.asyncio
async def test_cancelled_propagates(monkeypatch):
    """Engine relies on CancelledError flowing through to short-circuit retries."""

    class _CancelStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise asyncio.CancelledError()

    async def fake_acompletion(**kwargs):
        return _CancelStream()

    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hi"}],
        model="minimax-m2.7",
    )
    with pytest.raises(asyncio.CancelledError):
        _ = [d async for d in stream]

    assert result.incomplete_reason is None  # not set on cancellation
