from types import SimpleNamespace

import pytest

from app.libs.llm.providers import litellm_client


class FakeAPIError(Exception):
    status_code = 503


def _fake_response():
    return SimpleNamespace(
        id="official-response-id",
        model="MiniMax-M2.7",
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8),
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content="ok",
                    tool_calls=None,
                    reasoning_details=None,
                    thinking_content=None,
                    reasoning_content=None,
                    reasoning=None,
                ),
            )
        ],
    )


class _FakeStream:
    def __init__(self):
        self._chunks = iter(
            [
                SimpleNamespace(
                    id="official-stream-id",
                    model="MiniMax-M2.7",
                    usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8),
                    choices=[
                        SimpleNamespace(
                            finish_reason="stop",
                            delta=SimpleNamespace(
                                content="ok",
                                tool_calls=None,
                                reasoning_details=None,
                                thinking_content=None,
                                reasoning_content=None,
                                reasoning=None,
                            ),
                        )
                    ],
                )
            ]
        )

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration from None


@pytest.fixture
def minimax_fallback_env(monkeypatch):
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "")
    monkeypatch.setattr(litellm_client.settings, "MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setattr(litellm_client.settings, "MINIMAX_BASE_URL", "https://api.minimax.io/v1")
    monkeypatch.setattr(litellm_client.settings, "MOONSHOT_API_KEY", "")
    monkeypatch.setattr(litellm_client.settings, "ZHIPU_API_KEY", "")
    monkeypatch.setattr(litellm_client.settings, "SILICONFLOW_API_KEY", "")
    monkeypatch.setattr(litellm_client.litellm.exceptions, "APIError", FakeAPIError)


@pytest.mark.asyncio
async def test_chat_falls_back_to_openrouter_after_minimax_official(monkeypatch, minimax_fallback_env):
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise FakeAPIError("openrouter down")
        return _fake_response()

    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    result = await litellm_client.LiteLLMClient().chat(
        [{"role": "user", "content": "hello"}],
        model="minimax-m2.7",
    )

    assert result.content == "ok"
    assert result.provider_channel == "openrouter"
    assert result.provider_name == "OpenRouter"
    assert [call["model"] for call in calls] == [
        "openai/MiniMax-M2.7",
        "openrouter/minimax/minimax-m2.7",
    ]
    assert calls[0]["api_key"] == "minimax-key"
    assert calls[0]["api_base"] == "https://api.minimax.io/v1"
    assert calls[1]["api_key"] == "openrouter-key"
    assert calls[1]["api_base"] == "https://openrouter.ai/api/v1"


@pytest.mark.asyncio
async def test_stream_falls_back_to_openrouter_after_minimax_official(monkeypatch, minimax_fallback_env):
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise FakeAPIError("openrouter down")
        return _FakeStream()

    monkeypatch.setattr(litellm_client.litellm, "acompletion", fake_acompletion)

    stream, result = await litellm_client.LiteLLMClient().stream_chat(
        [{"role": "user", "content": "hello"}],
        model="minimax-m2.7",
    )

    chunks = [delta async for delta in stream]

    assert [chunk.content for chunk in chunks] == ["ok"]
    assert result.model == "MiniMax-M2.7"
    assert result.content == "ok"
    assert result.provider_channel == "openrouter"
    assert result.provider_name == "OpenRouter"
    assert [call["model"] for call in calls] == [
        "openai/MiniMax-M2.7",
        "openrouter/minimax/minimax-m2.7",
    ]
    assert calls[1]["stream"] is True
    assert calls[1]["stream_options"] == {"include_usage": True}


def test_kimi_candidates_follow_domestic_provider_priority(monkeypatch):
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "bailian-key")
    monkeypatch.setattr(
        litellm_client.settings,
        "ALIYUN_BAILIAN_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setattr(litellm_client.settings, "MOONSHOT_API_KEY", "moonshot-key")
    monkeypatch.setattr(litellm_client.settings, "MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    monkeypatch.setattr(litellm_client.settings, "SILICONFLOW_API_KEY", "silicon-key")
    monkeypatch.setattr(litellm_client.settings, "SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "openrouter-key")

    candidates = litellm_client._model_candidates("kimi-k2.6")

    assert [candidate["channel"] for candidate in candidates] == [
        "aliyun-bailian",
        "moonshot-official",
        "siliconflow",
        "openrouter",
    ]
    assert [candidate["model"] for candidate in candidates] == [
        "openai/kimi/kimi-k2.6",
        "openai/kimi-k2.6",
        "openai/Pro/moonshotai/Kimi-K2.6",
        "openrouter/moonshotai/kimi-k2.6",
    ]
    assert candidates[1]["temperature"] == 1.0


def test_provider_channel_names_cover_domestic_routes():
    assert litellm_client.PROVIDER_CHANNEL_NAMES["aliyun-bailian"] == "阿里百炼"
    assert litellm_client.PROVIDER_CHANNEL_NAMES["moonshot-official"] == "Kimi 官方"
    assert litellm_client.PROVIDER_CHANNEL_NAMES["zhipu-official"] == "智谱官方"
    assert litellm_client.PROVIDER_CHANNEL_NAMES["minimax-official"] == "MiniMax 官方"
