"""
Quick local test for LiteLLM + OpenRouter provider.

Usage:
    cd server
    python -m app.libs.llm.providers.test_llm              # uses .env.dev
    python -m app.libs.llm.providers.test_llm --stream      # streaming mode
    python -m app.libs.llm.providers.test_llm --env .env.production  # specify env
    python -m app.libs.llm.providers.test_llm --model kimi-k2.5
    python -m app.libs.llm.providers.test_llm --model glm-5.1 --thinking

    # Override via env vars:
    OPENROUTER_API_KEY=sk-or-xxx \
        python -m app.libs.llm.providers.test_llm
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))


def load_env(env_file: str) -> None:
    path = os.path.join(os.path.dirname(__file__), "../../../..", env_file)
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


def _print_client_info(client, model: str, prompt: str | None = None) -> None:
    from app.libs.llm.providers.litellm_client import (
        OPENROUTER_MODEL_MAP,
        _model_candidates,
        _resolve_model,
    )

    del client
    route = " -> ".join(candidate["channel"] for candidate in _model_candidates(model))
    print(f"  Provider : LiteLLM routed providers")
    print(f"  Route    : {route}")
    print(f"  Model    : {model} -> {_resolve_model(model)}")
    if prompt:
        print(f"  Prompt   : {prompt}")
    print(f"  Available: {', '.join(OPENROUTER_MODEL_MAP.keys())}")
    print("-" * 60)


async def test_chat(model: str, prompt: str, *, thinking: bool = False) -> None:
    from app.libs.llm.providers.litellm_client import LiteLLMClient

    client = LiteLLMClient()
    _print_client_info(client, model, prompt)
    print(f"  Thinking mode  : {'on' if thinking else 'off'}")

    start = time.perf_counter()
    resp = await client.chat(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        thinking_enabled=thinking,
    )
    elapsed = time.perf_counter() - start

    print(f"  Content        : {resp.content}")
    if resp.thinking_content:
        tc = resp.thinking_content
        tail = "..." if len(tc) > 200 else ""
        print(f"  Thinking       : {tc[:200]}{tail}")
    print(f"  Finish reason  : {resp.finish_reason}")
    print(f"  Tokens (in/out): {resp.input_tokens} / {resp.output_tokens}")
    print(f"  Model returned : {resp.model}")
    print(f"  Request ID     : {resp.request_id}")
    print(f"  Elapsed        : {elapsed:.2f}s")


async def test_stream(model: str, prompt: str, *, thinking: bool = False) -> None:
    from app.libs.llm.providers.litellm_client import LiteLLMClient

    client = LiteLLMClient()
    _print_client_info(client, model, prompt)
    print(f"  Thinking mode  : {'on' if thinking else 'off'}")

    start = time.perf_counter()
    stream, result = await client.stream_chat(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        thinking_enabled=thinking,
    )

    print("  Streaming: ", end="", flush=True)
    async for delta in stream:
        if delta.content:
            print(delta.content, end="", flush=True)
    print()

    elapsed = time.perf_counter() - start
    print("-" * 60)
    if result.thinking_content:
        tc = result.thinking_content
        tail = "..." if len(tc) > 500 else ""
        print(f"  Thinking (acc) : {tc[:500]}{tail}")
    print(f"  Finish reason  : {result.finish_reason}")
    print(f"  Tokens (in/out): {result.input_tokens} / {result.output_tokens}")
    print(f"  Model returned : {result.model}")
    print(f"  Request ID     : {result.request_id}")
    print(f"  Elapsed        : {elapsed:.2f}s")


async def test_tool_call(model: str) -> None:
    from app.libs.llm.providers.litellm_client import LiteLLMClient

    client = LiteLLMClient()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                },
            },
        }
    ]

    _print_client_info(client, model)

    resp = await client.chat(
        messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
        model=model,
        tools=tools,
    )

    if resp.tool_calls:
        for i, tc in enumerate(resp.tool_calls):
            print(f"  Tool call [{i}]: {tc['function']['name']}({tc['function']['arguments']})")
    else:
        print(f"  No tool calls, content: {resp.content}")
    print(f"  Finish reason: {resp.finish_reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test LiteLLM + OpenRouter provider locally")
    parser.add_argument("--env", default=".env.dev", help="Env file to load (default: .env.dev)")
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="Model short name (gpt-4o, kimi-k2.5, kimi-k2.6, glm-5, glm-5.1, ling-2.6-flash, mimo-v2.5-pro, minimax-m2.5, minimax-m2.7, step-3.5-flash, grok-4.20, grok-4.20-multi-agent)",
    )
    parser.add_argument("--prompt", default="你好，请用一句话介绍你自己。", help="Test prompt")
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Enable OpenRouter reasoning (needed for GLM/MiniMax visible chain-of-thought)",
    )
    parser.add_argument("--stream", action="store_true", help="Test streaming mode")
    parser.add_argument("--tool", action="store_true", help="Test tool calling")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    args = parser.parse_args()

    load_env(args.env)

    if args.all:
        print("=" * 60)
        print("[1/3] Non-streaming chat")
        print("=" * 60)
        asyncio.run(test_chat(args.model, args.prompt, thinking=args.thinking))
        print()
        print("=" * 60)
        print("[2/3] Streaming chat")
        print("=" * 60)
        asyncio.run(test_stream(args.model, args.prompt, thinking=args.thinking))
        print()
        print("=" * 60)
        print("[3/3] Tool calling")
        print("=" * 60)
        asyncio.run(test_tool_call(args.model))
    elif args.tool:
        print("=" * 60)
        print("Tool calling test")
        print("=" * 60)
        asyncio.run(test_tool_call(args.model))
    elif args.stream:
        print("=" * 60)
        print("Streaming chat test")
        print("=" * 60)
        asyncio.run(test_stream(args.model, args.prompt, thinking=args.thinking))
    else:
        print("=" * 60)
        print("Non-streaming chat test")
        print("=" * 60)
        asyncio.run(test_chat(args.model, args.prompt, thinking=args.thinking))

    print("\nDone!")


if __name__ == "__main__":
    main()


"""
# 普通对话测试（默认读 .env.dev，模型 gpt-4o）
python -m app.libs.llm.providers.test_llm

# 流式输出测试
python -m app.libs.llm.providers.test_llm --stream

# Tool calling 测试
python -m app.libs.llm.providers.test_llm --tool

# 全部测试
python -m app.libs.llm.providers.test_llm --all

# 指定模型
python -m app.libs.llm.providers.test_llm --model kimi-k2.5
python -m app.libs.llm.providers.test_llm --model glm-5 --stream
python -m app.libs.llm.providers.test_llm --model glm-5.1 --thinking --stream
python -m app.libs.llm.providers.test_llm --model ling-2.6-flash
python -m app.libs.llm.providers.test_llm --model mimo-v2.5-pro
python -m app.libs.llm.providers.test_llm --model minimax-m2.5
python -m app.libs.llm.providers.test_llm --model minimax-m2.7 --prompt "解释量子计算"
python -m app.libs.llm.providers.test_llm --model minimax-m2.7 --thinking
python -m app.libs.llm.providers.test_llm --model step-3.5-flash

# 使用生产环境配置
python -m app.libs.llm.providers.test_llm --env .env.production

# 临时覆盖 API 配置
OPENROUTER_API_KEY=sk-or-xxx \
python -m app.libs.llm.providers.test_llm --model gpt-4o
"""
