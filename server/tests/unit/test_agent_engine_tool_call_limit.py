import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.libs.llm.base import LLMStreamResult
from app.schemas.agent import EngineConfig
from app.services import agent_engine_service as svc


DEFAULT_TOOL_CALL_LIMIT_REPLY = (
    "抱歉，本轮回复已达到工具调用上限，暂时无法继续处理。请简化问题、缩小查询范围或稍后重试。"
)


def test_tool_call_limit_reply_uses_configured_content():
    markdown_reply = "**工具调用已达上限**\n\n请缩小范围后重试。"
    config = EngineConfig(
        conversation_settings={
            "tool_call_limit_reply": {
                "enabled": True,
                "content": markdown_reply,
            }
        }
    )

    assert svc._tool_call_limit_reply_content(config) == markdown_reply


def test_tool_call_limit_reply_uses_default_when_blank_if_disabled():
    config = EngineConfig(
        conversation_settings={
            "tool_call_limit_reply": {
                "enabled": False,
                "content": "   ",
            }
        }
    )

    assert svc._tool_call_limit_reply_content(config) == DEFAULT_TOOL_CALL_LIMIT_REPLY


def test_parse_tool_arguments_repairs_truncated_json_object():
    raw_arguments = (
        '{"query": "80W LED 高功率", "brief": "查询80W功率级别的LED产品", '
        '"filter": {"slice_meta": [{"field": "productType", "op": "eq", '
        '"value": "LED"}, {"field": "power_w", "op": "ge", "value": 70}, '
        '{"field": "power_w", "op": "le", "value": 90}]}'
    )

    result = svc._parse_tool_arguments(
        raw_arguments,
        tool_name="knowledge_search",
        tool_call_id="call_search",
    )

    assert result["query"] == "80W LED 高功率"
    assert result["brief"] == "查询80W功率级别的LED产品"
    assert result["filter"]["slice_meta"][2] == {
        "field": "power_w",
        "op": "le",
        "value": 90,
    }


@pytest.mark.asyncio
async def test_build_history_uses_assistant_limit_reply(monkeypatch):
    async def fake_get_history_steps(db, conversation_id):
        return [
            {
                "round_number": 1,
                "step_order": 1,
                "step_type": "user_message",
                "content": "查一下资料",
                "status": "success",
            },
            {
                "round_number": 1,
                "step_order": 2,
                "step_type": "tool_call",
                "tool_call_id": "call_1",
                "tool_response": "工具结果",
                "status": "success",
            },
            {
                "round_number": 1,
                "step_order": 3,
                "step_type": "assistant_message",
                "content": "工具调用已达上限，请缩小范围后重试。",
                "status": "success",
                "metadata": {
                    "notice_type": "tool_call_limit",
                    "code": svc.TOOL_CALL_LIMIT_ERROR_CODE,
                },
            },
        ]

    monkeypatch.setattr(
        svc.ConversationStepRepository,
        "get_history_steps",
        fake_get_history_steps,
    )

    history = await svc._build_history(
        db=None,
        conversation_id=1,
        config=EngineConfig(),
        current_round=2,
    )

    assert history == [
        {"role": "user", "content": "查一下资料"},
        {"role": "assistant", "content": "工具调用已达上限，请缩小范围后重试。"},
    ]


@pytest.mark.asyncio
async def test_engine_repairs_truncated_tool_arguments_before_execute(monkeypatch):
    created_steps: list[dict] = []
    executed_args: list[dict] = []
    counter_updates: list[dict] = []

    async def fake_get_agent_by_id(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="T_TEST", engine_config={})

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="T_TEST",
            agent_id=7,
            round_count=0,
            title="已有标题",
            external_id="conv_search",
            source="api",
        )

    @asynccontextmanager
    async def fake_hold_round_lock(db, conv, conversation_id, client_message_id, **kwargs):
        yield 1, False

    async def fake_create_step(db, conversation_id, tenant_id, data):
        item = {**data, "id": len(created_steps) + 1}
        item.setdefault("metadata", {})
        item["metadata_"] = item["metadata"]
        created_steps.append(item)
        return SimpleNamespace(**item)

    async def fake_increment_counters(db, conversation_id, **kwargs):
        counter_updates.append(kwargs)

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
        assert tool_name == "knowledge_search"
        executed_args.append(tool_args)
        return "搜索结果"

    async def fake_build_history(db, conversation_id, config, current_round):
        return []

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
        def __init__(self):
            self.calls = 0

        async def stream_chat(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                arguments = json.dumps(
                    {
                        "query": "80W LED 高功率",
                        "brief": "查询80W功率级别的LED产品",
                        "filter": {
                            "slice_meta": [
                                {
                                    "field": "productType",
                                    "op": "eq",
                                    "value": "LED",
                                },
                                {"field": "power_w", "op": "ge", "value": 70},
                                {"field": "power_w", "op": "le", "value": 90},
                            ]
                        },
                    },
                    ensure_ascii=False,
                )[:-1]
                return EmptyStream(), LLMStreamResult(
                    content="",
                    thinking_content="",
                    tool_calls=[{
                        "id": "call_search",
                        "type": "function",
                        "function": {
                            "name": "knowledge_search",
                            "arguments": arguments,
                        },
                    }],
                    finish_reason="tool_calls",
                    model=kwargs.get("model"),
                    incomplete_reason=None,
                )

            assert messages[-1] == {
                "role": "tool",
                "tool_call_id": "call_search",
                "content": "搜索结果",
            }
            return EmptyStream(), LLMStreamResult(
                content="推荐这款 80W LED。",
                thinking_content="",
                tool_calls=[],
                finish_reason="stop",
                model=kwargs.get("model"),
                incomplete_reason=None,
            )

    monkeypatch.setattr(svc.AgentRepository, "get_by_id", fake_get_agent_by_id)
    monkeypatch.setattr(svc.ConversationRepository, "get_by_id", fake_get_conversation_by_id)
    monkeypatch.setattr(svc, "_hold_round_lock", fake_hold_round_lock)
    monkeypatch.setattr(svc, "_create_step", fake_create_step)
    monkeypatch.setattr(svc.ConversationRepository, "increment_counters", fake_increment_counters)
    monkeypatch.setattr(svc, "_load_tools", fake_load_tools)
    monkeypatch.setattr(svc, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(svc, "_build_history", fake_build_history)
    monkeypatch.setattr(svc.ConversationStepRepository, "update", fake_update_step)
    monkeypatch.setattr(
        svc.AgentMessagePreprocessor,
        "prepare_current_user_message",
        fake_prepare_current_user_message,
    )
    monkeypatch.setattr(svc, "create_llm_client", lambda: FakeLLMClient())

    frames = []
    async for raw in svc.AgentEngineService._run_chat_round_impl(
        db=SimpleNamespace(),
        agent_id=7,
        user_message="推荐一个 80W LED",
        conversation_id=123,
    ):
        frames.append(raw)

    assert executed_args == [{
        "query": "80W LED 高功率",
        "brief": "查询80W功率级别的LED产品",
        "filter": {
            "slice_meta": [
                {"field": "productType", "op": "eq", "value": "LED"},
                {"field": "power_w", "op": "ge", "value": 70},
                {"field": "power_w", "op": "le", "value": 90},
            ]
        },
    }]
    tool_steps = [step for step in created_steps if step["step_type"] == "tool_call"]
    assert tool_steps[0]["tool_arguments"] == executed_args[0]
    assert tool_steps[0]["brief"] == "查询80W功率级别的LED产品"
    assert {"tool_call_count": 1} in counter_updates
    assert any("\nevent: done\n" in frame for frame in frames)


@pytest.mark.asyncio
async def test_tool_call_limit_closes_round_with_assistant_message(monkeypatch):
    created_steps: list[dict] = []
    counter_updates: list[dict] = []
    tool_call_seq = 0
    markdown_reply = "**工具调用已达上限**\n\n请缩小范围后重试。"

    async def fake_get_agent_by_id(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="T_TEST", engine_config={
            "context": {
                "max_tool_loop_rounds": 2,
            },
            "conversation_settings": {
                "tool_call_limit_reply": {
                    "enabled": True,
                    "content": markdown_reply,
                }
            }
        })

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="T_TEST",
            agent_id=7,
            round_count=0,
            title="已有标题",
            external_id="conv_limit",
        )

    @asynccontextmanager
    async def fake_hold_round_lock(db, conv, conversation_id, client_message_id, **kwargs):
        yield 1, False

    async def fake_create_step(db, conversation_id, tenant_id, data):
        item = {**data, "id": len(created_steps) + 1}
        item.setdefault("metadata", {})
        item["metadata_"] = item["metadata"]
        created_steps.append(item)
        return SimpleNamespace(**item)

    async def fake_increment_counters(db, conversation_id, **kwargs):
        counter_updates.append(kwargs)

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

    async def fake_build_history(db, conversation_id, config, current_round):
        return []

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
            nonlocal tool_call_seq
            tool_call_seq += 1
            result = LLMStreamResult(
                content="",
                thinking_content="",
                tool_calls=[{
                    "id": f"call_{tool_call_seq}",
                    "type": "function",
                    "function": {
                        "name": "knowledge_search",
                        "arguments": json.dumps({"brief": "查询知识库"}, ensure_ascii=False),
                    },
                }],
                finish_reason="tool_calls",
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
    monkeypatch.setattr(svc, "_build_history", fake_build_history)
    monkeypatch.setattr(svc.ConversationStepRepository, "update", fake_update_step)
    monkeypatch.setattr(
        svc.AgentMessagePreprocessor,
        "prepare_current_user_message",
        fake_prepare_current_user_message,
    )
    monkeypatch.setattr(svc, "create_llm_client", lambda: FakeLLMClient())

    frames = []
    async for raw in svc.AgentEngineService._run_chat_round_impl(
        db=SimpleNamespace(),
        agent_id=7,
        user_message="查资料",
        conversation_id=123,
    ):
        frames.append(raw)

    assistant_steps = [
        step for step in created_steps
        if step["step_type"] == "assistant_message"
    ]
    tool_steps = [
        step for step in created_steps
        if step["step_type"] == "tool_call"
    ]
    assert tool_call_seq == 2
    assert len(tool_steps) == 2
    assert len(assistant_steps) == 1
    assert assistant_steps[0]["content"] == markdown_reply
    assert assistant_steps[0]["metadata"] == {
        "notice_type": "tool_call_limit",
        "code": svc.TOOL_CALL_LIMIT_ERROR_CODE,
        "generated_by": "system",
    }
    assert {"round_count": 1} in counter_updates
    assert any("\nevent: done\n" in frame for frame in frames)
    assert not any("\nevent: error\n" in frame for frame in frames)


@pytest.mark.asyncio
async def test_tool_call_limit_resume_done_preserves_code(monkeypatch):
    async def fake_get_agent_by_id(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="T_TEST", engine_config={})

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="T_TEST",
            agent_id=7,
            round_count=1,
            title="已有标题",
            external_id="conv_limit",
        )

    @asynccontextmanager
    async def fake_hold_round_lock(db, conv, conversation_id, client_message_id, **kwargs):
        yield 1, True

    async def fake_get_steps_by_round(db, conversation_id, round_number):
        return [
            SimpleNamespace(
                id=1,
                step_type="user_message",
                content="查资料",
                metadata_={},
            ),
            SimpleNamespace(
                id=2,
                step_type="assistant_message",
                content="工具调用已达上限，请缩小范围后重试。",
                metadata_={
                    "notice_type": "tool_call_limit",
                    "code": svc.TOOL_CALL_LIMIT_ERROR_CODE,
                },
            ),
        ]

    monkeypatch.setattr(svc.AgentRepository, "get_by_id", fake_get_agent_by_id)
    monkeypatch.setattr(svc.ConversationRepository, "get_by_id", fake_get_conversation_by_id)
    monkeypatch.setattr(svc, "_hold_round_lock", fake_hold_round_lock)
    monkeypatch.setattr(
        svc.ConversationStepRepository,
        "get_steps_by_round",
        fake_get_steps_by_round,
    )

    frames = []
    async for raw in svc.AgentEngineService._run_chat_round_impl(
        db=SimpleNamespace(),
        agent_id=7,
        user_message="查资料",
        conversation_id=123,
        resume=True,
    ):
        frames.append(raw)

    done_frame = next(frame for frame in frames if "\nevent: done\n" in frame)
    payload = json.loads(
        next(line for line in done_frame.splitlines() if line.startswith("data:"))[5:]
    )
    assert payload["code"] == svc.TOOL_CALL_LIMIT_ERROR_CODE
    assert payload["finish_reason"] == svc.TOOL_CALL_LIMIT_FINISH_REASON
    assert payload["reply"] == "工具调用已达上限，请缩小范围后重试。"
