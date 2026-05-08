"""
Check OpenAI-compatible connectivity for configured domestic LLM providers.

Usage:
    cd server
    python3 scripts/check_llm_provider_connectivity.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ENV_FILE = Path(__file__).resolve().parents[1] / ".env.dev"
TIMEOUT_SEC = 30


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def chat_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def extract_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def error_summary(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text[:500]

    error = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(error, dict):
        message = error.get("message") or error.get("code") or error
        return str(message)[:500]
    return json.dumps(parsed, ensure_ascii=False)[:500]


def call_chat(
    name: str,
    model: str,
    key_var: str,
    base_url_var: str,
    temperature: float = 0,
) -> bool:
    api_key = os.getenv(key_var, "")
    base_url = os.getenv(base_url_var, "")
    if not api_key or not base_url:
        print(f"[SKIP] {name:<22} model={model} missing {key_var}/{base_url_var}")
        return False

    body = {
        "model": model,
        "messages": [{"role": "user", "content": "请只回复 OK"}],
        "temperature": temperature,
        "max_tokens": 16,
        "stream": False,
    }
    request = urllib.request.Request(
        chat_url(base_url),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(
            f"[FAIL] {name:<22} model={model} "
            f"status={exc.code} error={error_summary(exc.read())}"
        )
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name:<22} model={model} error={exc}")
        return False

    text = extract_text(payload)
    usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
    total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
    token_part = f" tokens={total_tokens}" if total_tokens is not None else ""
    print(f"[OK]   {name:<22} model={model}{token_part} reply={text[:80]!r}")
    return True


def main() -> int:
    load_env_file(ENV_FILE)

    checks = [
        ("aliyun-bailian", "MiniMax/MiniMax-M2.7", "ALIYUN_BAILIAN_API_KEY", "ALIYUN_BAILIAN_BASE_URL"),
        ("aliyun-bailian", "kimi/kimi-k2.6", "ALIYUN_BAILIAN_API_KEY", "ALIYUN_BAILIAN_BASE_URL"),
        ("aliyun-bailian", "glm-5.1", "ALIYUN_BAILIAN_API_KEY", "ALIYUN_BAILIAN_BASE_URL"),
        ("minimax-official", "MiniMax-M2.7", "MINIMAX_API_KEY", "MINIMAX_BASE_URL"),
        ("moonshot-official", "kimi-k2.6", "MOONSHOT_API_KEY", "MOONSHOT_BASE_URL", 1),
        ("zhipu-official", "glm-5.1", "ZHIPU_API_KEY", "ZHIPU_BASE_URL"),
    ]

    ok_count = 0
    for check in checks:
        ok_count += int(call_chat(*check))

    total = len(checks)
    failed = total - ok_count
    print(f"\nSummary: {ok_count}/{total} succeeded, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
