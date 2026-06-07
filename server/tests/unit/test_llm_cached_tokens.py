from types import SimpleNamespace

from app.libs.llm.base import extract_cached_tokens_from_usage


def test_extract_cached_tokens_from_openai_prompt_details_dict():
    usage = {
        "prompt_tokens": 120,
        "prompt_tokens_details": {"cached_tokens": 45},
    }

    assert extract_cached_tokens_from_usage(usage) == 45


def test_extract_cached_tokens_from_litellm_prompt_details_object():
    usage = SimpleNamespace(
        prompt_tokens=120,
        prompt_tokens_details=SimpleNamespace(cached_tokens=32),
    )

    assert extract_cached_tokens_from_usage(usage) == 32


def test_extract_cached_tokens_from_provider_alias():
    usage = {"prompt_tokens": 120, "cache_read_input_tokens": 28}

    assert extract_cached_tokens_from_usage(usage) == 28


def test_extract_cached_tokens_defaults_to_zero_when_missing():
    usage = {"prompt_tokens": 120}

    assert extract_cached_tokens_from_usage(usage) == 0
