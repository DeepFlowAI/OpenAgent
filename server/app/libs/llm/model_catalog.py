"""UI-facing LLM model catalog and env-driven filtering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiModelOption:
    value: str
    label: str


# Default catalog when LLM_UI_MODELS is unset (matches legacy frontend list).
DEFAULT_UI_MODELS: tuple[UiModelOption, ...] = (
    UiModelOption("deepseek-v4-pro", "DeepSeek V4 Pro"),
    UiModelOption("deepseek-v4-flash", "DeepSeek V4 Flash"),
    UiModelOption("kimi-k2.6", "Kimi K2.6"),
    UiModelOption("glm-5.1", "GLM-5.1"),
    UiModelOption("mimo-v2.5-pro", "MiMo V2.5 Pro"),
    UiModelOption("minimax-m2.7", "MiniMax M2.7"),
)

_DEFAULT_LABELS = {m.value: m.label for m in DEFAULT_UI_MODELS}


def parse_llm_ui_models(raw: str) -> list[UiModelOption]:
    """Parse LLM_UI_MODELS env: comma-separated ``id`` or ``id:Label`` entries."""
    text = (raw or "").strip()
    if not text:
        return list(DEFAULT_UI_MODELS)

    options: list[UiModelOption] = []
    seen: set[str] = set()
    for part in text.split(","):
        entry = part.strip()
        if not entry:
            continue
        if ":" in entry:
            value, label = entry.split(":", 1)
            value, label = value.strip(), label.strip()
        else:
            value = entry
            label = _DEFAULT_LABELS.get(value, value)
        if not value or value in seen:
            continue
        seen.add(value)
        options.append(UiModelOption(value=value, label=label or value))
    return options


def ui_models_as_dicts(raw: str) -> list[dict[str, str]]:
    return [{"value": m.value, "label": m.label} for m in parse_llm_ui_models(raw)]
