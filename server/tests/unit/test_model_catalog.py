from app.libs.llm.model_catalog import parse_llm_ui_models, ui_models_as_dicts
from app.libs.llm.providers import litellm_client


def test_parse_llm_ui_models_default_catalog():
    models = parse_llm_ui_models("")
    assert len(models) >= 10
    assert models[0].value == "gpt-4o"


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
