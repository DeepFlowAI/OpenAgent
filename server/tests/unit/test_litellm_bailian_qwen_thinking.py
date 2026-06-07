"""Bailian qwen models must explicitly disable thinking when the caller asks
for thinking-off (DashScope defaults qwen3 thinking ON, which burns ~1k
reasoning tokens even for the few-char conversation title summary)."""
from app.libs.llm.providers import litellm_client


def _apply(thinking_enabled: bool) -> dict:
    kwargs: dict = {}
    litellm_client._apply_thinking(
        kwargs,
        thinking_enabled=thinking_enabled,
        resolved_model="openai/qwen3.6-flash",
        channel="aliyun-bailian",
    )
    return kwargs


def test_bailian_qwen_disables_thinking_when_off():
    kwargs = _apply(False)
    assert kwargs.get("extra_body", {}).get("enable_thinking") is False


def test_bailian_qwen_enables_thinking_when_on():
    kwargs = _apply(True)
    assert kwargs.get("extra_body", {}).get("enable_thinking") is True
