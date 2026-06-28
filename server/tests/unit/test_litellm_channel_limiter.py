import logging

from app.libs.llm.providers import litellm_client as lc


def _reset_limiter(monkeypatch, *, global_limit: int, overrides: str = "") -> None:
    monkeypatch.setattr(lc.settings, "LLM_CHANNEL_CONCURRENCY", global_limit)
    monkeypatch.setattr(lc.settings, "LLM_CHANNEL_CONCURRENCY_OVERRIDES", overrides)
    lc._channel_limit_overrides = None
    lc._channel_semaphores.clear()


def test_channel_limiter_uses_global_limit(monkeypatch):
    _reset_limiter(monkeypatch, global_limit=2)

    sem = lc._channel_semaphore("openrouter")

    assert sem is lc._channel_semaphore("openrouter")
    assert sem is not None
    assert sem._value == 2


def test_channel_override_zero_disables_limit_for_one_channel(monkeypatch):
    _reset_limiter(
        monkeypatch,
        global_limit=3,
        overrides="openrouter:0,aliyun-bailian:2",
    )

    assert lc._channel_semaphore("openrouter") is None
    assert lc._channel_semaphore("aliyun-bailian")._value == 2
    assert lc._channel_semaphore("deepseek-official")._value == 3


def test_channel_override_logs_and_ignores_bad_entries(monkeypatch, caplog):
    _reset_limiter(
        monkeypatch,
        global_limit=4,
        overrides="bad,nope:x,:3,neg:-1,openrouter:1",
    )

    with caplog.at_level(logging.WARNING):
        parsed = lc._parse_channel_overrides()

    assert parsed == {"openrouter": 1}
    assert "Ignoring malformed LLM channel override" in caplog.text
    assert "Ignoring non-integer LLM channel override" in caplog.text
    assert "Ignoring invalid LLM channel override" in caplog.text
