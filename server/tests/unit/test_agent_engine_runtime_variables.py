import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.libs.llm.base import LLMStreamResult
from app.schemas.agent import EngineConfig
from app.services import agent_engine_service as svc


def _step(
    round_number: int,
    step_order: int,
    step_type: str,
    **kwargs,
) -> dict:
    return {
        "round_number": round_number,
        "step_order": step_order,
        "step_type": step_type,
        "status": "success",
        **kwargs,
    }


@pytest.mark.asyncio
async def test_build_history_exposes_loaded_and_tool_trace_round_counts(monkeypatch):
    async def fake_get_history_steps(db, conversation_id):
        return [
            _step(1, 1, "user_message", content="u1"),
            _step(1, 2, "assistant_message", content="a1"),
            _step(2, 1, "user_message", content="u2"),
            _step(2, 2, "llm_call", response_tool_calls=[{"id": "call_2"}]),
            _step(2, 3, "tool_call", tool_call_id="call_2", tool_response="tool 2"),
            _step(2, 4, "assistant_message", content="a2"),
            _step(3, 1, "user_message", content="u3"),
            _step(3, 2, "llm_call", response_tool_calls=[{"id": "call_3"}]),
            _step(3, 3, "tool_call", tool_call_id="call_3", tool_response="tool 3"),
            _step(3, 4, "assistant_message", content="a3"),
        ]

    monkeypatch.setattr(
        svc.ConversationStepRepository,
        "get_history_steps",
        fake_get_history_steps,
    )

    history = await svc._build_history(
        db=None,
        conversation_id=1,
        config=EngineConfig(
            context={
                "max_rounds": 2,
                "history_tool_rounds": 1,
                "recent_full_tool_responses": 4,
            }
        ),
        current_round=4,
    )

    assert history.loaded_round_count == 2
    assert history.tool_trace_round_count == 1
    assert [message["role"] for message in history] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert history[0]["content"] == "u2"
    assert history[-2]["content"] == "tool 3"


@pytest.mark.asyncio
async def test_build_history_counts_only_rounds_with_actual_tool_trace(monkeypatch):
    async def fake_get_history_steps(db, conversation_id):
        return [
            _step(1, 1, "user_message", content="u1"),
            _step(1, 2, "llm_call", response_tool_calls=[{"id": "call_1"}]),
            _step(1, 3, "tool_call", tool_call_id="call_1", tool_response="tool 1"),
            _step(1, 4, "assistant_message", content="a1"),
            _step(2, 1, "user_message", content="u2"),
            _step(2, 2, "assistant_message", content="a2"),
        ]

    monkeypatch.setattr(
        svc.ConversationStepRepository,
        "get_history_steps",
        fake_get_history_steps,
    )

    history = await svc._build_history(
        db=None,
        conversation_id=1,
        config=EngineConfig(
            context={
                "max_rounds": 2,
                "history_tool_rounds": 1,
                "recent_full_tool_responses": 4,
            }
        ),
        current_round=3,
    )

    assert history.loaded_round_count == 2
    assert history.tool_trace_round_count == 0
    assert [message["role"] for message in history] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


@pytest.mark.asyncio
async def test_build_history_replays_reasoning_content_for_assistant_message(monkeypatch):
    """Thinking models require the prior turn's reasoning_content to be passed
    back. The final assistant_message step stores only content, so it must
    recover thinking_content from its parent llm_call step.
    """
    async def fake_get_history_steps(db, conversation_id):
        return [
            _step(1, 1, "user_message", content="u1"),
            _step(1, 2, "llm_call", id=10, thinking_content="think1"),
            _step(1, 3, "assistant_message", content="a1", parent_step_id=10),
        ]

    monkeypatch.setattr(
        svc.ConversationStepRepository,
        "get_history_steps",
        fake_get_history_steps,
    )

    history = await svc._build_history(
        db=None,
        conversation_id=1,
        config=EngineConfig(
            context={
                "max_rounds": 0,
                "history_tool_rounds": 1,
                "recent_full_tool_responses": 4,
            }
        ),
        current_round=2,
    )

    assert [message["role"] for message in history] == ["user", "assistant"]
    assert history[1]["content"] == "a1"
    assert history[1]["reasoning_content"] == "think1"


@pytest.mark.asyncio
async def test_build_history_applies_recent_full_tool_response_limit(monkeypatch):
    async def fake_get_history_steps(db, conversation_id):
        return [
            _step(1, 1, "user_message", content="u1"),
            _step(1, 2, "llm_call", response_tool_calls=[{"id": "plain_call"}]),
            _step(
                1,
                3,
                "tool_call",
                tool_type="notebook",
                tool_call_id="plain_call",
                tool_response="plain tool response",
            ),
            _step(1, 4, "assistant_message", content="a1"),
            _step(2, 1, "user_message", content="u2"),
            _step(2, 2, "llm_call", response_tool_calls=[{"id": "old_call"}]),
            _step(
                2,
                3,
                "tool_call",
                tool_type="search",
                tool_call_id="old_call",
                tool_response="old archived response",
                metadata={"tool_response_id": "sr_old"},
            ),
            _step(2, 4, "assistant_message", content="a2"),
            _step(3, 1, "user_message", content="u3"),
            _step(3, 2, "llm_call", response_tool_calls=[{"id": "new_call"}]),
            _step(
                3,
                3,
                "tool_call",
                tool_type="search",
                tool_call_id="new_call",
                tool_response="new archived response",
                metadata={"tool_response_id": "sr_new"},
            ),
            _step(3, 4, "assistant_message", content="a3"),
        ]

    monkeypatch.setattr(
        svc.ConversationStepRepository,
        "get_history_steps",
        fake_get_history_steps,
    )

    history = await svc._build_history(
        db=None,
        conversation_id=1,
        config=EngineConfig(
            context={
                "max_rounds": 0,
                "history_tool_rounds": 3,
                "recent_full_tool_responses": 1,
            }
        ),
        current_round=4,
    )

    tool_messages = [message for message in history if message["role"] == "tool"]
    assert tool_messages == [
        {
            "role": "tool",
            "tool_call_id": "plain_call",
            "content": "plain tool response",
        },
        {
            "role": "tool",
            "tool_call_id": "old_call",
            "content": "搜索结果已归档。工具响应 id（tool response id）：sr_old",
        },
        {
            "role": "tool",
            "tool_call_id": "new_call",
            "content": "new archived response",
        },
    ]


def test_runtime_template_vars_track_tool_progress():
    history = svc._HistoryMessages(
        [],
        loaded_round_count=2,
        tool_trace_round_count=1,
    )

    variables = svc._runtime_template_vars(
        config=EngineConfig(
            context={
                "max_rounds": 2,
                "history_tool_rounds": 1,
                "recent_full_tool_responses": 4,
                "max_tool_loop_rounds": 7,
            }
        ),
        round_number=3,
        history=history,
        llm_call_index=2,
        current_round_messages=[
            {"role": "user", "content": "查资料"},
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        ],
    )

    assert variables["context_max_rounds"] == "2"
    assert variables["context_history_tool_rounds"] == "1"
    assert variables["context_recent_full_tool_responses"] == "4"
    assert variables["conversation_round_number"] == "3"
    assert variables["history_loaded_round_count"] == "2"
    assert variables["history_tool_trace_round_count"] == "1"
    assert variables["llm_call_index_in_round"] == "2"
    assert variables["completed_tool_call_count_in_round"] == "1"
    assert variables["next_tool_call_index_in_round"] == "2"
    assert variables["max_tool_loop_rounds"] == "7"
    assert variables["remaining_tool_loop_rounds"] == "6"


@pytest.mark.asyncio
async def test_system_prompt_runtime_variables_rerender_each_llm_call(monkeypatch):
    captured_system_prompts: list[str] = []
    created_steps: list[dict] = []

    async def fake_get_agent_by_id(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="T_TEST", engine_config={
            "system_prompt": (
                "round={{conversation_round_number}} "
                "history={{history_loaded_round_count}} "
                "trace={{history_tool_trace_round_count}} "
                "llm={{llm_call_index_in_round}} "
                "done_tools={{completed_tool_call_count_in_round}} "
                "next_tool={{next_tool_call_index_in_round}} "
                "max={{max_tool_loop_rounds}} "
                "remaining={{remaining_tool_loop_rounds}}"
            ),
            "context": {
                "max_rounds": 2,
                "history_tool_rounds": 1,
                "recent_full_tool_responses": 4,
                "max_tool_loop_rounds": 3,
            },
            "selected_tool_ids": [1],
        })

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="T_TEST",
            agent_id=7,
            round_count=2,
            title="已有标题",
            external_id="conv_runtime",
        )

    @asynccontextmanager
    async def fake_hold_round_lock(db, conv, conversation_id, client_message_id, **kwargs):
        yield 3, False

    async def fake_create_step(db, conversation_id, tenant_id, data):
        item = {**data, "id": len(created_steps) + 1}
        item.setdefault("metadata", {})
        item["metadata_"] = item["metadata"]
        created_steps.append(item)
        return SimpleNamespace(**item)

    async def fake_increment_counters(db, conversation_id, **kwargs):
        return None

    async def fake_load_tools(db, agent_id, selected_tool_ids):
        return [{
            "id": 1,
            "name": "knowledge_search",
            "description": "查询知识库",
            "parameters_schema": {"type": "object", "properties": {}},
            "tool_type": "search",
            "config": {},
        }]

    async def fake_execute_tool(tool_name, tool_args, tools_defs, tool_ctx):
        return "工具结果"

    async def fake_get_history_steps(db, conversation_id):
        return [
            _step(1, 1, "user_message", content="u1"),
            _step(1, 2, "assistant_message", content="a1"),
            _step(2, 1, "user_message", content="u2"),
            _step(2, 2, "llm_call", response_tool_calls=[{"id": "old_call"}]),
            _step(2, 3, "tool_call", tool_call_id="old_call", tool_response="old tool"),
            _step(2, 4, "assistant_message", content="a2"),
        ]

    async def fake_prepare_current_user_message(db, tenant_id, agent_id, text):
        return SimpleNamespace(text=text, metadata={})

    async def fake_update_step(db, step, data):
        for key, value in data.items():
            setattr(step, key if key != "metadata" else "metadata_", value)
        return step

    class EmptyStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class FakeLLMClient:
        async def stream_chat(self, messages, **kwargs):
            captured_system_prompts.append(messages[0]["content"])
            if len(captured_system_prompts) == 1:
                result = LLMStreamResult(
                    content="",
                    thinking_content="",
                    tool_calls=[{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "knowledge_search",
                            "arguments": json.dumps(
                                {"brief": "查询知识库"},
                                ensure_ascii=False,
                            ),
                        },
                    }],
                    finish_reason="tool_calls",
                    model=kwargs.get("model"),
                    incomplete_reason=None,
                )
            else:
                result = LLMStreamResult(
                    content="完成",
                    thinking_content="",
                    tool_calls=[],
                    finish_reason="stop",
                    model=kwargs.get("model"),
                    incomplete_reason=None,
                )
            return EmptyStream(), result

    monkeypatch.setattr(svc.AgentRepository, "get_by_id", fake_get_agent_by_id)
    monkeypatch.setattr(svc.ConversationRepository, "get_by_id", fake_get_conversation_by_id)
    monkeypatch.setattr(svc, "_hold_round_lock", fake_hold_round_lock)
    monkeypatch.setattr(svc, "_create_step", fake_create_step)
    monkeypatch.setattr(svc.ConversationRepository, "increment_counters", fake_increment_counters)
    monkeypatch.setattr(svc, "_load_tools", fake_load_tools)
    monkeypatch.setattr(svc, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(
        svc.ConversationStepRepository,
        "get_history_steps",
        fake_get_history_steps,
    )
    monkeypatch.setattr(svc.ConversationStepRepository, "update", fake_update_step)
    monkeypatch.setattr(
        svc.AgentMessagePreprocessor,
        "prepare_current_user_message",
        fake_prepare_current_user_message,
    )
    monkeypatch.setattr(svc, "create_llm_client", lambda: FakeLLMClient())

    async for _raw in svc.AgentEngineService._run_chat_round_impl(
        db=SimpleNamespace(),
        agent_id=7,
        user_message="查资料",
        conversation_id=123,
    ):
        pass

    assert captured_system_prompts == [
        "round=3 history=2 trace=1 llm=1 done_tools=0 next_tool=1 max=3 remaining=3",
        "round=3 history=2 trace=1 llm=2 done_tools=1 next_tool=2 max=3 remaining=2",
    ]


def test_thinking_for_round_is_consistent_within_a_round():
    """Thinking must be scoped to the whole round, not toggled per tool-loop
    call. With the first-screen latency config (first round off, later rounds
    on), round 1 stays off for ALL its calls so a mid-loop thinking-on
    continuation never resends a thinking-off assistant turn without
    reasoning_content (DeepSeek 400). Round 2+ follows subsequent_rounds.
    """
    fast_first = SimpleNamespace(
        first_round_thinking=False, subsequent_rounds_thinking=True
    )
    assert svc._thinking_for_round(fast_first, 1) is False
    assert svc._thinking_for_round(fast_first, 2) is True
    assert svc._thinking_for_round(fast_first, 5) is True

    think_first = SimpleNamespace(
        first_round_thinking=True, subsequent_rounds_thinking=False
    )
    assert svc._thinking_for_round(think_first, 1) is True
    assert svc._thinking_for_round(think_first, 2) is False
