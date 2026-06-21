"""Regression tests for streaming LLM span finalization on early consumer close.

Bug: when the SSE consumer abandons the stream early (client disconnect, user
navigation, tool-loop short-circuit), the traced async generator receives a
``GeneratorExit``. That bypasses the ``except``/``else`` branches that record the
actually-routed channel, so the span used to close with ``gen_ai.system`` still
holding the up-front model-name guess (e.g. ``glm-5.1`` -> ``"zhipu"``) and the
real channel lost. These tests pin the finalized behavior.
"""
from contextlib import contextmanager

from app.libs.llm.base import BaseLLMClient, LLMStreamDelta, LLMStreamResult
from app.libs.observability import helpers, llm_tracer


class RecordingSpan:
    def __init__(self):
        self.attributes: dict = {}
        self.status: str = "unset"
        self.status_message: str | None = None

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_status_ok(self):
        self.status = "ok"

    def set_status_error(self, message):
        self.status = "error"
        self.status_message = message

    def add_event(self, name, attributes=None):
        pass


class RecordingProvider:
    def __init__(self):
        self.spans: list[RecordingSpan] = []

    @contextmanager
    def start_llm_span(self, name, attributes=None):
        span = RecordingSpan()
        if attributes:
            span.attributes.update(attributes)
        self.spans.append(span)
        yield span

    def get_current_span(self):
        return self.spans[-1] if self.spans else RecordingSpan()


class _FakeStreamClient(BaseLLMClient):
    """Inner client whose stream yields forever until the consumer stops."""

    def __init__(self, result: LLMStreamResult):
        self._result = result

    async def chat(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError

    async def stream_chat(self, messages, **kwargs):
        result = self._result

        async def _gen():
            # provider_channel is set by real providers right after the upstream
            # stream starts (before the first chunk is yielded). Mirror that.
            result.model = "glm-5.1"
            while True:
                yield LLMStreamDelta(content="x")

        return _gen(), result


def _use_recording_provider(monkeypatch) -> RecordingProvider:
    provider = RecordingProvider()
    monkeypatch.setattr(helpers, "get_provider", lambda: provider)
    return provider


async def test_stream_cancel_records_real_channel_not_model_guess(monkeypatch):
    provider = _use_recording_provider(monkeypatch)
    result = LLMStreamResult(provider_channel="aliyun-bailian", provider_name="阿里百炼")
    client = llm_tracer.wrap_llm_client(_FakeStreamClient(result))

    stream, _ = await client.stream_chat([{"role": "user", "content": "hi"}], model="glm-5.1")

    agen = stream.__aiter__()
    await agen.__anext__()  # consume one chunk, then abandon the stream
    await agen.aclose()

    span = provider.spans[-1]
    # The up-front guess would have left this as "zhipu"; finalization must
    # overwrite it with the channel that actually served the request.
    assert span.attributes["gen_ai.system"] == "aliyun-bailian"
    assert span.attributes["gen_ai.provider.channel"] == "aliyun-bailian"
    assert span.attributes["gen_ai.cancel.reason"] == "client_cancelled"
    # Cancellation is not a server error — keep it out of error/retry dashboards.
    assert span.status == "unset"


async def test_stream_normal_completion_still_ok(monkeypatch):
    provider = _use_recording_provider(monkeypatch)
    result = LLMStreamResult(
        provider_channel="siliconflow", provider_name="硅基流动", finish_reason="stop"
    )

    class _FiniteClient(BaseLLMClient):
        async def chat(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        async def stream_chat(self, messages, **kwargs):
            async def _gen():
                result.model = "glm-5.1"
                yield LLMStreamDelta(content="hello")

            return _gen(), result

    client = llm_tracer.wrap_llm_client(_FiniteClient())
    stream, _ = await client.stream_chat([{"role": "user", "content": "hi"}], model="glm-5.1")
    async for _ in stream:
        pass

    span = provider.spans[-1]
    assert span.attributes["gen_ai.system"] == "siliconflow"
    assert span.status == "ok"
    assert "gen_ai.cancel.reason" not in span.attributes
