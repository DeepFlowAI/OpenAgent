"""Pin the structured provider-fallback log contract.

The daily report aggregates LLM degradations by querying otel_logs for the
stable body phrase and the flat ``log_attributes`` fields emitted here. If this
format changes, the report's per-model counts silently break — so lock it down.
"""
import logging

from app.libs.llm.providers import litellm_client


def test_provider_fallback_log_emits_structured_fields(caplog):
    with caplog.at_level(logging.WARNING, logger=litellm_client.logger.name):
        litellm_client._log_provider_fallback(
            model="glm-5.1",
            from_channel="aliyun-bailian",
            to_channel="zhipu-official",
            reason="connect_timeout",
            mode="stream",
        )

    records = [r for r in caplog.records if "LLM provider fallback" in r.getMessage()]
    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.WARNING
    # Flat attributes flow into OTel log_attributes for SQL aggregation.
    assert rec.llm_provider_fallback == "1"
    assert rec.fallback_model == "glm-5.1"
    assert rec.fallback_from == "aliyun-bailian"
    assert rec.fallback_to == "zhipu-official"
    assert rec.fallback_reason == "connect_timeout"
    assert rec.fallback_mode == "stream"
    # Human-readable body keeps the model inline too.
    assert "model=glm-5.1" in rec.getMessage()


def test_provider_fallback_log_truncates_long_detail(caplog):
    long_detail = "x" * 5000
    with caplog.at_level(logging.WARNING, logger=litellm_client.logger.name):
        litellm_client._log_provider_fallback(
            model="glm-5.1",
            from_channel="aliyun-bailian",
            to_channel="openrouter",
            reason="api_error",
            mode="sync",
            detail=long_detail,
        )

    rec = next(r for r in caplog.records if "LLM provider fallback" in r.getMessage())
    assert len(rec.getMessage()) < 5000 + 200


def test_degraded_channel_error_alert_is_throttled_then_refires(caplog, monkeypatch):
    """A persistently-down paid channel must raise an actionable ERROR (for alerts)
    at most once per cooldown window, not one ERROR per fallback/round."""
    monkeypatch.setattr(litellm_client, "_last_fallback_alert", {})
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(litellm_client.time, "monotonic", lambda: fake_now["t"])

    def fire():
        litellm_client._log_provider_fallback(
            model="deepseek-v4-pro",
            from_channel="deepseek-official",
            to_channel="aliyun-bailian",
            reason="api_error",
            mode="stream",
            detail="litellm.BadRequestError: OpenAIException - Insufficient Balance",
        )

    with caplog.at_level(logging.ERROR, logger=litellm_client.logger.name):
        fire()  # first fallback in window -> ERROR fires
        fire()  # still within cooldown -> throttled (no ERROR)
        fake_now["t"] += litellm_client._FALLBACK_ALERT_COOLDOWN_SEC + 1
        fire()  # cooldown elapsed -> ERROR fires again

    errors = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "LLM channel degraded" in r.getMessage()
    ]
    assert len(errors) == 2
    assert errors[0].llm_channel_degraded == "1"
    assert errors[0].degraded_channel == "deepseek-official"
    assert errors[0].degraded_reason == "api_error"
