from app.libs.llm.model_catalog import parse_llm_ui_models, ui_models_as_dicts
from app.libs.llm.providers import litellm_client


def test_parse_llm_ui_models_default_catalog():
    models = parse_llm_ui_models("")
    assert len(models) >= 10
    assert models[0].value == "gpt-4o"
    assert ("deepseek-v4-pro", "DeepSeek V4 Pro") in [
        (m.value, m.label) for m in models
    ]
    assert ("deepseek-v4-pro-official", "DeepSeek V4 Pro 官方") in [
        (m.value, m.label) for m in models
    ]
    assert ("deepseek-v4-flash", "deepseek v4 flash 官方") in [
        (m.value, m.label) for m in models
    ]


def test_parse_llm_ui_models_custom_entries():
    models = parse_llm_ui_models("kimi-k2.6:Kimi K2.6,glm-5.1")
    assert [(m.value, m.label) for m in models] == [
        ("kimi-k2.6", "Kimi K2.6"),
        ("glm-5.1", "GLM-5.1"),
    ]


def test_ui_models_as_dicts():
    assert ui_models_as_dicts("minimax-m2.7:MiniMax M2.7") == [
        {"value": "minimax-m2.7", "label": "MiniMax M2.7"},
    ]


def test_model_candidates_bailian_channel_only(monkeypatch):
    monkeypatch.setattr(
        litellm_client.settings, "LLM_PROVIDER_CHANNELS", "aliyun-bailian"
    )
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "bailian-key")
    monkeypatch.setattr(
        litellm_client.settings,
        "ALIYUN_BAILIAN_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "or-key")

    candidates = litellm_client._model_candidates("kimi-k2.6")
    assert len(candidates) == 1
    assert candidates[0]["channel"] == "aliyun-bailian"
    assert candidates[0]["model"] == "openai/kimi/kimi-k2.6"

    glm = litellm_client._model_candidates("glm-5.1")
    assert glm[0]["model"] == "openai/ZHIPU/GLM-5.1"

    deepseek = litellm_client._model_candidates("deepseek-v4-pro")
    assert len(deepseek) == 1
    assert deepseek[0]["channel"] == "aliyun-bailian"
    assert deepseek[0]["model"] == "openai/deepseek-v4-pro"


def test_model_candidates_multi_channel_fallback(monkeypatch):
    monkeypatch.setattr(
        litellm_client.settings,
        "LLM_PROVIDER_CHANNELS",
        "aliyun-bailian,openrouter",
    )
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "bailian-key")
    monkeypatch.setattr(
        litellm_client.settings,
        "ALIYUN_BAILIAN_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "or-key")

    candidates = litellm_client._model_candidates("kimi-k2.6")
    assert [c["channel"] for c in candidates] == ["aliyun-bailian", "openrouter"]


def test_model_candidates_deepseek_uses_official_when_bailian_unavailable(monkeypatch):
    monkeypatch.setattr(litellm_client.settings, "LLM_PROVIDER_CHANNELS", "")
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "")
    monkeypatch.setattr(litellm_client.settings, "DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr(
        litellm_client.settings,
        "DEEPSEEK_API_BASE_URL",
        "https://api.deepseek.com",
    )
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "or-key")

    candidates = litellm_client._model_candidates("deepseek-v4-pro")

    assert [c["channel"] for c in candidates] == ["deepseek-official", "openrouter"]
    assert [c["model"] for c in candidates] == [
        "openai/deepseek-v4-pro",
        "openrouter/deepseek/deepseek-v4-pro",
    ]
    assert candidates[0]["api_key"] == "deepseek-key"
    assert candidates[0]["api_base"] == "https://api.deepseek.com"


def test_model_candidates_deepseek_prefers_bailian_when_available(monkeypatch):
    monkeypatch.setattr(litellm_client.settings, "LLM_PROVIDER_CHANNELS", "")
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "bailian-key")
    monkeypatch.setattr(
        litellm_client.settings,
        "ALIYUN_BAILIAN_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setattr(litellm_client.settings, "DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr(
        litellm_client.settings,
        "DEEPSEEK_API_BASE_URL",
        "https://api.deepseek.com",
    )
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "or-key")

    candidates = litellm_client._model_candidates("deepseek-v4-pro")

    assert [c["channel"] for c in candidates] == [
        "aliyun-bailian",
        "deepseek-official",
        "openrouter",
    ]
    assert candidates[0]["model"] == "openai/deepseek-v4-pro"
    assert candidates[0]["api_key"] == "bailian-key"
    assert (
        candidates[0]["api_base"]
        == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


def test_model_candidates_deepseek_official_option_skips_bailian(monkeypatch):
    monkeypatch.setattr(litellm_client.settings, "LLM_PROVIDER_CHANNELS", "")
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "bailian-key")
    monkeypatch.setattr(
        litellm_client.settings,
        "ALIYUN_BAILIAN_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setattr(litellm_client.settings, "DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr(
        litellm_client.settings,
        "DEEPSEEK_API_BASE_URL",
        "https://api.deepseek.com",
    )
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "or-key")

    candidates = litellm_client._model_candidates("deepseek-v4-pro-official")

    assert [c["channel"] for c in candidates] == ["deepseek-official", "openrouter"]
    assert [c["model"] for c in candidates] == [
        "openai/deepseek-v4-pro",
        "openrouter/deepseek/deepseek-v4-pro",
    ]
    assert candidates[0]["api_key"] == "deepseek-key"
    assert candidates[0]["api_base"] == "https://api.deepseek.com"


def test_model_candidates_deepseek_official_option_not_mapped_to_bailian(monkeypatch):
    monkeypatch.setattr(
        litellm_client.settings,
        "LLM_PROVIDER_CHANNELS",
        "aliyun-bailian,openrouter",
    )
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "bailian-key")
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "or-key")

    candidates = litellm_client._model_candidates("deepseek-v4-pro-official")

    assert [c["channel"] for c in candidates] == ["openrouter"]
    assert candidates[0]["model"] == "openrouter/deepseek/deepseek-v4-pro"


def test_model_candidates_deepseek_flash_uses_official(monkeypatch):
    monkeypatch.setattr(litellm_client.settings, "LLM_PROVIDER_CHANNELS", "")
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "bailian-key")
    monkeypatch.setattr(litellm_client.settings, "DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr(
        litellm_client.settings,
        "DEEPSEEK_API_BASE_URL",
        "https://api.deepseek.com",
    )
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "or-key")

    candidates = litellm_client._model_candidates("deepseek-v4-flash")

    assert [c["channel"] for c in candidates] == ["deepseek-official", "openrouter"]
    assert [c["model"] for c in candidates] == [
        "openai/deepseek-v4-flash",
        "openrouter/deepseek/deepseek-v4-flash",
    ]
    assert candidates[0]["api_key"] == "deepseek-key"
    assert candidates[0]["api_base"] == "https://api.deepseek.com"


def test_model_candidates_deepseek_flash_not_mapped_to_bailian(monkeypatch):
    monkeypatch.setattr(
        litellm_client.settings,
        "LLM_PROVIDER_CHANNELS",
        "aliyun-bailian,openrouter",
    )
    monkeypatch.setattr(litellm_client.settings, "ALIYUN_BAILIAN_API_KEY", "bailian-key")
    monkeypatch.setattr(litellm_client.settings, "OPENROUTER_API_KEY", "or-key")

    candidates = litellm_client._model_candidates("deepseek-v4-flash")

    assert [c["channel"] for c in candidates] == ["openrouter"]
    assert candidates[0]["model"] == "openrouter/deepseek/deepseek-v4-flash"


def test_deepseek_thinking_request_params_preserve_reasoning_content():
    candidate = {
        "channel": "deepseek-official",
        "model": "openai/deepseek-v4-pro",
        "api_key": "deepseek-key",
        "api_base": "https://api.deepseek.com",
    }
    kwargs = litellm_client._request_kwargs(
        candidate,
        messages=[
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "keep this",
                "tool_calls": [],
            }
        ],
        temperature=0.01,
        top_p=0.85,
        max_tokens=4096,
        stream=False,
    )
    litellm_client._apply_thinking(
        kwargs,
        True,
        candidate["model"],
        candidate["channel"],
    )

    assert kwargs["messages"][0]["reasoning_content"] == "keep this"
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert kwargs["reasoning_effort"] == "high"

    disabled_kwargs = litellm_client._request_kwargs(
        candidate,
        messages=[],
        temperature=0.01,
        top_p=0.85,
        max_tokens=4096,
        stream=False,
    )
    litellm_client._apply_thinking(
        disabled_kwargs,
        False,
        candidate["model"],
        candidate["channel"],
    )
    assert disabled_kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in disabled_kwargs


def test_bailian_deepseek_thinking_request_params_preserve_reasoning_content():
    candidate = {
        "channel": "aliyun-bailian",
        "model": "openai/deepseek-v4-pro",
        "api_key": "bailian-key",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }
    kwargs = litellm_client._request_kwargs(
        candidate,
        messages=[
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "keep this",
                "tool_calls": [],
            }
        ],
        temperature=0.01,
        top_p=0.85,
        max_tokens=4096,
        stream=False,
    )
    litellm_client._apply_thinking(
        kwargs,
        True,
        candidate["model"],
        candidate["channel"],
    )

    assert kwargs["messages"][0]["reasoning_content"] == "keep this"
    assert kwargs["extra_body"] == {"enable_thinking": True}
    assert kwargs["reasoning_effort"] == "high"

    disabled_kwargs = litellm_client._request_kwargs(
        candidate,
        messages=[],
        temperature=0.01,
        top_p=0.85,
        max_tokens=4096,
        stream=False,
    )
    litellm_client._apply_thinking(
        disabled_kwargs,
        False,
        candidate["model"],
        candidate["channel"],
    )
    assert disabled_kwargs["extra_body"] == {"enable_thinking": False}
    assert "reasoning_effort" not in disabled_kwargs


def test_kimi_channels_preserve_reasoning_content():
    for channel, model in [
        ("moonshot-official", "openai/kimi-k2.6"),
        ("aliyun-bailian", "openai/kimi/kimi-k2.6"),
        ("siliconflow", "openai/Pro/moonshotai/Kimi-K2.6"),
        ("openrouter", "openrouter/moonshotai/kimi-k2.6"),
    ]:
        kwargs = litellm_client._request_kwargs(
            {
                "channel": channel,
                "model": model,
                "api_key": "key",
                "api_base": "https://example.test/v1",
            },
            messages=[
                {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "keep kimi thinking",
                    "tool_calls": [],
                }
            ],
            temperature=0.01,
            top_p=0.85,
            max_tokens=4096,
            stream=False,
        )

        assert kwargs["messages"][0]["reasoning_content"] == "keep kimi thinking"


def test_non_reasoning_channels_strip_reasoning_content():
    kwargs = litellm_client._request_kwargs(
        {
            "channel": "openrouter",
            "model": "openrouter/deepseek/deepseek-v4-pro",
            "api_key": "or-key",
            "api_base": "https://openrouter.ai/api/v1",
        },
        messages=[
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "provider-specific",
                "tool_calls": [],
            }
        ],
        temperature=0.01,
        top_p=0.85,
        max_tokens=4096,
        stream=False,
    )

    assert "reasoning_content" not in kwargs["messages"][0]
