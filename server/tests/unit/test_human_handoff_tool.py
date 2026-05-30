"""
Unit tests for the human handoff system tool.
"""
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from datetime import datetime

import pytest

from app.core.exceptions import ValidationError
from app.libs.llm.base import LLMStreamResult
from app.models.service_hours import ServiceHours
from app.repositories.agent_tool_repository import AgentToolRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.service_hours_repository import ServiceHoursRepository
from app.schemas.agent_tool import (
    AgentToolCreate,
    AgentToolUpdate,
    HUMAN_HANDOFF_TOOL_NAME,
    HUMAN_HANDOFF_TOOL_TYPE,
    build_human_handoff_parameters_schema,
)
from app.schemas.conversation_step import ToolResultSubmit
from app.services import agent_engine_service as engine_module
from app.services import conversation_step_service as step_service_module
from app.services import human_handoff_event_service
from app.services.agent_tool_service import AgentToolService
from app.services.conversation_step_service import ConversationStepService
from app.services.tool_executors.base import ToolContext
from app.services.tool_executors.human_handoff_executor import HumanHandoffToolExecutor


def test_human_handoff_schema_respects_route_field_switches():
    schema = build_human_handoff_parameters_schema({
        "route_fields": {
            "agent_group_id": True,
            "agent_id": False,
            "business_type": False,
        }
    })

    props = schema["properties"]
    assert "brief" in props
    assert "reason" in props
    assert "urgency" in props
    assert "agent_group_id" in props
    assert "agent_id" not in props
    assert "business_type" not in props
    assert schema["required"] == ["brief", "reason"]


@pytest.mark.asyncio
async def test_create_rejects_manual_human_handoff_tool():
    with pytest.raises(ValidationError):
        await AgentToolService.create(
            object(),
            1,
            "tenant-a",
            AgentToolCreate(
                name="human_handoff",
                tool_type=HUMAN_HANDOFF_TOOL_TYPE,
            ),
        )


@pytest.mark.asyncio
async def test_create_rejects_reserved_human_handoff_name():
    with pytest.raises(ValidationError):
        await AgentToolService.create(
            object(),
            1,
            "tenant-a",
            AgentToolCreate(
                name=HUMAN_HANDOFF_TOOL_NAME,
                tool_type="search",
            ),
        )


@pytest.mark.asyncio
async def test_update_rejects_reserved_human_handoff_name(monkeypatch):
    item = SimpleNamespace(
        id=10,
        agent_id=1,
        tool_type="search",
        name="knowledge_search",
        is_system=False,
        config={},
    )

    async def fake_get_by_id(db, tool_id):
        return item

    async def fail_get_by_agent_and_name(db, agent_id, name):
        raise AssertionError("reserved name should be rejected before duplicate lookup")

    monkeypatch.setattr(AgentToolRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        AgentToolRepository,
        "get_by_agent_and_name",
        fail_get_by_agent_and_name,
    )

    with pytest.raises(ValidationError):
        await AgentToolService.update(
            object(),
            10,
            1,
            AgentToolUpdate(name=HUMAN_HANDOFF_TOOL_NAME),
        )


@pytest.mark.asyncio
async def test_update_human_handoff_system_tool_rebuilds_schema(monkeypatch):
    item = SimpleNamespace(
        id=9,
        agent_id=1,
        tool_type=HUMAN_HANDOFF_TOOL_TYPE,
        name="human_handoff",
        is_system=True,
        description="old",
        config={},
    )
    calls = {}

    async def fake_get_by_id(db, tool_id):
        calls["tool_id"] = tool_id
        return item

    async def fake_update(db, target, data):
        calls["update"] = data
        for key, value in data.items():
            setattr(target, key, value)
        return target

    monkeypatch.setattr(AgentToolRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(AgentToolRepository, "update", fake_update)

    result = await AgentToolService.update(
        object(),
        9,
        1,
        AgentToolUpdate(
            description="Route to support",
            config={
                "service_hours_id": "12",
                "route_fields": {
                    "agent_group_id": True,
                    "agent_id": True,
                    "business_type": False,
                },
            },
        ),
    )

    assert calls["tool_id"] == 9
    assert result.description == "Route to support"
    assert calls["update"]["config"]["service_hours_id"] == 12
    props = calls["update"]["parameters_schema"]["properties"]
    assert "agent_group_id" in props
    assert "agent_id" in props
    assert "business_type" not in props


@pytest.mark.asyncio
async def test_runtime_filter_removes_handoff_for_non_api_conversation():
    tools = [
        {"name": "human_handoff", "tool_type": HUMAN_HANDOFF_TOOL_TYPE, "config": {}},
        {"name": "knowledge_search", "tool_type": "search", "config": {}},
    ]

    filtered = await engine_module._filter_runtime_tools(
        object(),
        tools,
        conversation_source="websdk",
        tenant_id="tenant-a",
    )

    assert [tool["name"] for tool in filtered] == ["knowledge_search"]


@pytest.mark.asyncio
async def test_runtime_filter_treats_missing_service_hours_as_in_service(monkeypatch):
    async def fake_get_by_id(db, service_hours_id):
        return None

    monkeypatch.setattr(ServiceHoursRepository, "get_by_id", fake_get_by_id)
    tools = [
        {
            "name": "human_handoff",
            "tool_type": HUMAN_HANDOFF_TOOL_TYPE,
            "config": {"service_hours_id": 404},
        }
    ]

    filtered = await engine_module._filter_runtime_tools(
        object(),
        tools,
        conversation_source="api",
        tenant_id="tenant-a",
    )

    assert filtered == tools


@pytest.mark.asyncio
async def test_runtime_filter_removes_handoff_outside_service_hours(monkeypatch):
    service_hours = ServiceHours(
        id=12,
        tenant_id="tenant-a",
        name="Support",
        timezone="Asia/Shanghai",
        weekly_periods=[{"day_of_week": 0, "start": "09:00", "end": "18:00"}],
        holidays=[],
        makeup_days=[],
    )

    async def fake_get_by_id(db, service_hours_id):
        return service_hours

    monkeypatch.setattr(ServiceHoursRepository, "get_by_id", fake_get_by_id)
    tools = [
        {
            "name": "human_handoff",
            "tool_type": HUMAN_HANDOFF_TOOL_TYPE,
            "config": {"service_hours_id": 12},
        }
    ]

    filtered = await engine_module._filter_runtime_tools(
        object(),
        tools,
        conversation_source="api",
        tenant_id="tenant-a",
        moment=datetime.fromisoformat("2026-05-18T20:00:00+08:00"),
    )

    assert filtered == []


@pytest.mark.asyncio
async def test_human_handoff_executor_requires_external_tool_result(monkeypatch):
    async def fake_get_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="tenant-a",
            agent_id=3,
            source="api",
        )

    monkeypatch.setattr(ConversationRepository, "get_by_id", fake_get_by_id)

    executor = HumanHandoffToolExecutor()
    result = await executor.execute(
        {"brief": "用户要求人工", "reason": "投诉升级", "urgency": "high"},
        {},
        ToolContext(
            db=object(),  # type: ignore[arg-type]
            conversation_id=7,
            tenant_id="tenant-a",
            agent_id=3,
            conversation_source="api",
        ),
    )

    assert 'status="requires_action"' in result
    assert "conversation tool-results API" in result


def test_human_handoff_error_result_marks_tool_call_step_error():
    fields = engine_module._tool_call_status_fields(
        {"tool_type": HUMAN_HANDOFF_TOOL_TYPE},
        '<human_handoff_response status="error" code="invalid_arguments">'
        "brief is required"
        "</human_handoff_response>",
    )

    assert fields == {
        "status": "error",
        "error_message": "invalid_arguments: brief is required",
    }

    assert engine_module._tool_call_status_fields(
        {"tool_type": HUMAN_HANDOFF_TOOL_TYPE},
        '<human_handoff_response status="recorded"></human_handoff_response>',
    ) == {}


@pytest.mark.asyncio
async def test_engine_waits_for_external_human_handoff_result(monkeypatch):
    created_steps: list[dict] = []
    counter_updates: list[dict] = []

    async def fake_get_agent_by_id(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="tenant-a", engine_config={})

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="tenant-a",
            agent_id=3,
            round_count=0,
            title="已有标题",
            external_id="conv_handoff",
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
            "id": 9,
            "name": "human_handoff",
            "description": "Request human support.",
            "parameters_schema": build_human_handoff_parameters_schema({}),
            "tool_type": HUMAN_HANDOFF_TOOL_TYPE,
            "config": {
                "route_fields": {
                    "agent_group_id": True,
                    "agent_id": False,
                    "business_type": False,
                }
            },
        }]

    async def fail_execute_tool(*args, **kwargs):
        raise AssertionError("human_handoff should wait for an external tool result")

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
            result = LLMStreamResult(
                content="",
                thinking_content="",
                tool_calls=[{
                    "id": "call_handoff",
                    "type": "function",
                    "function": {
                        "name": "human_handoff",
                        "arguments": json.dumps(
                            {"brief": "用户要求人工", "reason": "投诉升级"},
                            ensure_ascii=False,
                        ),
                    },
                }],
                finish_reason="tool_calls",
                model=kwargs.get("model"),
                incomplete_reason=None,
            )
            return EmptyStream(), result

    monkeypatch.setattr(engine_module.AgentRepository, "get_by_id", fake_get_agent_by_id)
    monkeypatch.setattr(engine_module.ConversationRepository, "get_by_id", fake_get_conversation_by_id)
    monkeypatch.setattr(engine_module, "_hold_round_lock", fake_hold_round_lock)
    monkeypatch.setattr(engine_module, "_create_step", fake_create_step)
    monkeypatch.setattr(engine_module.ConversationRepository, "increment_counters", fake_increment_counters)
    monkeypatch.setattr(engine_module, "_load_tools", fake_load_tools)
    monkeypatch.setattr(engine_module, "_execute_tool", fail_execute_tool)
    monkeypatch.setattr(engine_module, "_build_history", fake_build_history)
    monkeypatch.setattr(engine_module.ConversationStepRepository, "update", fake_update_step)
    monkeypatch.setattr(
        engine_module.AgentMessagePreprocessor,
        "prepare_current_user_message",
        fake_prepare_current_user_message,
    )
    monkeypatch.setattr(engine_module, "create_llm_client", lambda: FakeLLMClient())

    frames = []
    async for raw in engine_module.AgentEngineService._run_chat_round_impl(
        db=SimpleNamespace(),
        agent_id=3,
        user_message="我要人工",
        conversation_id=7,
    ):
        frames.append(raw)

    tool_steps = [step for step in created_steps if step["step_type"] == "tool_call"]
    assert len(tool_steps) == 1
    assert tool_steps[0]["tool_type"] == HUMAN_HANDOFF_TOOL_TYPE
    assert tool_steps[0]["status"] == "pending"
    assert tool_steps[0]["tool_response"] is None
    assert tool_steps[0]["metadata"]["requires_external_tool_result"] is True
    assert not [step for step in created_steps if step["step_type"] == "assistant_message"]
    assert {"tool_call_count": 1, "round_count": 1} in counter_updates
    assert any("\nevent: requires_action\n" in frame for frame in frames)
    assert any(
        "\nevent: done\n" in frame
        and engine_module.TOOL_RESULT_REQUIRED_FINISH_REASON in frame
        for frame in frames
    )


@pytest.mark.asyncio
async def test_engine_rejects_invalid_handoff_args_before_requires_action(monkeypatch):
    created_steps: list[dict] = []
    counter_updates: list[dict] = []

    async def fake_get_agent_by_id(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="tenant-a", engine_config={})

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="tenant-a",
            agent_id=3,
            round_count=0,
            title="已有标题",
            external_id="conv_handoff",
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
            "id": 9,
            "name": "human_handoff",
            "description": "Request human support.",
            "parameters_schema": build_human_handoff_parameters_schema({}),
            "tool_type": HUMAN_HANDOFF_TOOL_TYPE,
            "config": {},
        }]

    async def fail_execute_tool(*args, **kwargs):
        raise AssertionError("invalid human_handoff should be handled before executor")

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
                return EmptyStream(), LLMStreamResult(
                    content="",
                    thinking_content="",
                    tool_calls=[{
                        "id": "call_handoff",
                        "type": "function",
                        "function": {
                            "name": "human_handoff",
                            "arguments": json.dumps(
                                {"brief": "用户要求人工"},
                                ensure_ascii=False,
                            ),
                        },
                    }],
                    finish_reason="tool_calls",
                    model=kwargs.get("model"),
                    incomplete_reason=None,
                )
            assert messages[-1]["role"] == "tool"
            assert messages[-1]["tool_call_id"] == "call_handoff"
            assert 'status="error"' in messages[-1]["content"]
            return EmptyStream(), LLMStreamResult(
                content="我继续帮你处理。",
                thinking_content="",
                tool_calls=[],
                finish_reason="stop",
                model=kwargs.get("model"),
                incomplete_reason=None,
            )

    llm_client = FakeLLMClient()
    monkeypatch.setattr(engine_module.AgentRepository, "get_by_id", fake_get_agent_by_id)
    monkeypatch.setattr(engine_module.ConversationRepository, "get_by_id", fake_get_conversation_by_id)
    monkeypatch.setattr(engine_module, "_hold_round_lock", fake_hold_round_lock)
    monkeypatch.setattr(engine_module, "_create_step", fake_create_step)
    monkeypatch.setattr(engine_module.ConversationRepository, "increment_counters", fake_increment_counters)
    monkeypatch.setattr(engine_module, "_load_tools", fake_load_tools)
    monkeypatch.setattr(engine_module, "_execute_tool", fail_execute_tool)
    monkeypatch.setattr(engine_module, "_build_history", fake_build_history)
    monkeypatch.setattr(engine_module.ConversationStepRepository, "update", fake_update_step)
    monkeypatch.setattr(
        engine_module.AgentMessagePreprocessor,
        "prepare_current_user_message",
        fake_prepare_current_user_message,
    )
    monkeypatch.setattr(engine_module, "create_llm_client", lambda: llm_client)

    frames = []
    async for raw in engine_module.AgentEngineService._run_chat_round_impl(
        db=SimpleNamespace(),
        agent_id=3,
        user_message="我要人工",
        conversation_id=7,
    ):
        frames.append(raw)

    tool_steps = [step for step in created_steps if step["step_type"] == "tool_call"]
    assert len(tool_steps) == 1
    assert tool_steps[0]["tool_type"] == HUMAN_HANDOFF_TOOL_TYPE
    assert tool_steps[0]["status"] == "error"
    assert "reason is required" in tool_steps[0]["error_message"]
    assert not any("\nevent: requires_action\n" in frame for frame in frames)
    assert any("\nevent: tool_result\n" in frame for frame in frames)
    assert [step["step_type"] for step in created_steps][-1] == "assistant_message"
    assert {"tool_call_count": 1} in counter_updates


@pytest.mark.asyncio
async def test_engine_closes_mixed_handoff_tool_calls_as_error(monkeypatch):
    created_steps: list[dict] = []
    counter_updates: list[dict] = []
    executed_tools: list[tuple[str, dict]] = []

    async def fake_get_agent_by_id(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="tenant-a", engine_config={})

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="tenant-a",
            agent_id=3,
            round_count=0,
            title="已有标题",
            external_id="conv_handoff",
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
        return [
            {
                "id": 9,
                "name": "human_handoff",
                "description": "Request human support.",
                "parameters_schema": build_human_handoff_parameters_schema({}),
                "tool_type": HUMAN_HANDOFF_TOOL_TYPE,
                "config": {},
            },
            {
                "id": 10,
                "name": "knowledge_search",
                "description": "Search knowledge base.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
                "tool_type": "search",
                "config": {},
            },
        ]

    async def fake_execute_tool(tool_name, tool_args, tools_defs, tool_ctx):
        executed_tools.append((tool_name, tool_args))
        assert tool_name == "knowledge_search"
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
                return EmptyStream(), LLMStreamResult(
                    content="",
                    thinking_content="",
                    tool_calls=[
                        {
                            "id": "call_handoff",
                            "type": "function",
                            "function": {
                                "name": "human_handoff",
                                "arguments": json.dumps(
                                    {
                                        "brief": "用户要求人工",
                                        "reason": "投诉升级",
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        },
                        {
                            "id": "call_search",
                            "type": "function",
                            "function": {
                                "name": "knowledge_search",
                                "arguments": json.dumps(
                                    {"query": "订单状态"},
                                    ensure_ascii=False,
                                ),
                            },
                        },
                    ],
                    finish_reason="tool_calls",
                    model=kwargs.get("model"),
                    incomplete_reason=None,
                )

            tool_messages = [
                message for message in messages if message.get("role") == "tool"
            ]
            tool_contents = {
                message["tool_call_id"]: message["content"]
                for message in tool_messages
            }
            assert 'code="mixed_tool_calls"' in tool_contents["call_handoff"]
            assert 'status="error"' in tool_contents["call_handoff"]
            assert tool_contents["call_search"] == "搜索结果"
            return EmptyStream(), LLMStreamResult(
                content="已继续处理。",
                thinking_content="",
                tool_calls=[],
                finish_reason="stop",
                model=kwargs.get("model"),
                incomplete_reason=None,
            )

    llm_client = FakeLLMClient()
    monkeypatch.setattr(engine_module.AgentRepository, "get_by_id", fake_get_agent_by_id)
    monkeypatch.setattr(engine_module.ConversationRepository, "get_by_id", fake_get_conversation_by_id)
    monkeypatch.setattr(engine_module, "_hold_round_lock", fake_hold_round_lock)
    monkeypatch.setattr(engine_module, "_create_step", fake_create_step)
    monkeypatch.setattr(engine_module.ConversationRepository, "increment_counters", fake_increment_counters)
    monkeypatch.setattr(engine_module, "_load_tools", fake_load_tools)
    monkeypatch.setattr(engine_module, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(engine_module, "_build_history", fake_build_history)
    monkeypatch.setattr(engine_module.ConversationStepRepository, "update", fake_update_step)
    monkeypatch.setattr(
        engine_module.AgentMessagePreprocessor,
        "prepare_current_user_message",
        fake_prepare_current_user_message,
    )
    monkeypatch.setattr(engine_module, "create_llm_client", lambda: llm_client)

    frames = []
    async for raw in engine_module.AgentEngineService._run_chat_round_impl(
        db=SimpleNamespace(),
        agent_id=3,
        user_message="我要人工，也查一下订单",
        conversation_id=7,
    ):
        frames.append(raw)

    tool_steps = [step for step in created_steps if step["step_type"] == "tool_call"]
    assert len(tool_steps) == 2
    assert tool_steps[0]["tool_name"] == "human_handoff"
    assert tool_steps[0]["status"] == "error"
    assert "mixed_tool_calls" in tool_steps[0]["error_message"]
    assert tool_steps[1]["tool_name"] == "knowledge_search"
    assert tool_steps[1]["tool_response"] == "搜索结果"
    assert executed_tools == [("knowledge_search", {"query": "订单状态"})]
    assert not any("\nevent: requires_action\n" in frame for frame in frames)
    assert [step["step_type"] for step in created_steps][-1] == "assistant_message"
    assert counter_updates.count({"tool_call_count": 1}) == 2


@pytest.mark.asyncio
async def test_submit_tool_result_updates_step_and_creates_handoff_event(monkeypatch):
    calls = {}
    tool_step = SimpleNamespace(
        id=55,
        conversation_id=7,
        tenant_id="tenant-a",
        round_number=2,
        step_type="tool_call",
        tool_name="human_handoff",
        tool_type=HUMAN_HANDOFF_TOOL_TYPE,
        tool_call_id="call_handoff",
        tool_arguments={
            "brief": "用户要求人工",
            "reason": "投诉升级",
            "agent_group_id": "group-a",
            "business_type": "complaint",
        },
        tool_response=None,
        brief="用户要求人工",
        status="pending",
        error_message=None,
        metadata_={
            "tool_config": {
                "route_fields": {
                    "agent_group_id": True,
                    "agent_id": False,
                    "business_type": False,
                }
            }
        },
    )

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            external_id="conv_handoff",
            tenant_id="tenant-a",
            agent_id=3,
        )

    async def fake_get_tool_call_by_call_id(db, conversation_id, tool_call_id):
        calls["lookup"] = (conversation_id, tool_call_id)
        return tool_step

    async def fake_update(db, item, data):
        calls["update"] = data
        for key, value in data.items():
            setattr(item, key, value)
        return item

    async def fake_create_event(db, conv, agent_id, round_number, step, args, config):
        calls["event"] = {
            "conversation_id": conv.id,
            "agent_id": agent_id,
            "round_number": round_number,
            "tool_step_id": step.id,
            "args": args,
            "config": config,
        }
        return SimpleNamespace(id=99)

    monkeypatch.setattr(
        step_service_module.ConversationRepository,
        "get_by_id",
        fake_get_conversation_by_id,
    )
    monkeypatch.setattr(
        step_service_module.ConversationStepRepository,
        "get_tool_call_by_call_id",
        fake_get_tool_call_by_call_id,
    )
    monkeypatch.setattr(
        step_service_module.ConversationStepRepository,
        "update",
        fake_update,
    )
    monkeypatch.setattr(
        step_service_module,
        "create_human_handoff_event_step",
        fake_create_event,
    )

    result = await ConversationStepService.submit_tool_result(
        object(),
        7,
        "tenant-a",
        3,
        ToolResultSubmit(
            tool_call_id="call_handoff",
            status="handoff_success",
            message="queued in opendesk",
        ),
    )

    assert calls["lookup"] == (7, "call_handoff")
    assert calls["update"] == {
        "tool_response": "queued in opendesk",
        "status": "success",
        "error_message": None,
    }
    assert result.status == "success"
    assert calls["event"]["tool_step_id"] == 55
    assert calls["event"]["config"]["route_fields"]["agent_group_id"] is True


@pytest.mark.asyncio
async def test_submit_failed_tool_result_marks_error_without_handoff_event(monkeypatch):
    calls = {}
    tool_step = SimpleNamespace(
        id=55,
        conversation_id=7,
        tenant_id="tenant-a",
        round_number=2,
        step_type="tool_call",
        tool_name="human_handoff",
        tool_type=HUMAN_HANDOFF_TOOL_TYPE,
        tool_call_id="call_handoff",
        tool_arguments={"brief": "用户要求人工", "reason": "投诉升级"},
        tool_response=None,
        brief="用户要求人工",
        status="pending",
        error_message=None,
        metadata_={"tool_config": {}},
    )

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            external_id="conv_handoff",
            tenant_id="tenant-a",
            agent_id=3,
        )

    async def fake_get_tool_call_by_call_id(db, conversation_id, tool_call_id):
        return tool_step

    async def fake_update(db, item, data):
        calls["update"] = data
        for key, value in data.items():
            setattr(item, key, value)
        return item

    async def fail_create_event(*args, **kwargs):
        raise AssertionError("handoff_failed should not create handoff event")

    monkeypatch.setattr(
        step_service_module.ConversationRepository,
        "get_by_id",
        fake_get_conversation_by_id,
    )
    monkeypatch.setattr(
        step_service_module.ConversationStepRepository,
        "get_tool_call_by_call_id",
        fake_get_tool_call_by_call_id,
    )
    monkeypatch.setattr(
        step_service_module.ConversationStepRepository,
        "update",
        fake_update,
    )
    monkeypatch.setattr(
        step_service_module,
        "create_human_handoff_event_step",
        fail_create_event,
    )

    result = await ConversationStepService.submit_tool_result(
        object(),
        7,
        "tenant-a",
        3,
        ToolResultSubmit(
            tool_call_id="call_handoff",
            status="handoff_failed",
            message="当前没有可用客服，请继续由机器人处理。",
        ),
    )

    assert calls["update"] == {
        "tool_response": "当前没有可用客服，请继续由机器人处理。",
        "status": "error",
        "error_message": "当前没有可用客服，请继续由机器人处理。",
    }
    assert result.status == "error"


@pytest.mark.asyncio
async def test_failed_handoff_result_continues_llm(monkeypatch):
    created_steps: list[dict] = []
    counter_updates: list[dict] = []
    tool_step = SimpleNamespace(
        id=55,
        conversation_id=7,
        tenant_id="tenant-a",
        round_number=2,
        step_type="tool_call",
        tool_name="human_handoff",
        tool_type=HUMAN_HANDOFF_TOOL_TYPE,
        tool_call_id="call_handoff",
        tool_arguments={"brief": "用户要求人工", "reason": "投诉升级"},
        tool_response="当前没有可用客服，请继续由机器人处理。",
        brief="用户要求人工",
        status="error",
        error_message="当前没有可用客服，请继续由机器人处理。",
        metadata_={"tool_config": {}},
    )
    saved_steps = [
        SimpleNamespace(
            id=1,
            round_number=2,
            step_order=1,
            step_type="user_message",
            content="我要人工",
            status="success",
            metadata_={},
        ),
        SimpleNamespace(
            id=2,
            round_number=2,
            step_order=2,
            step_type="llm_call",
            content=None,
            response_tool_calls=[{
                "id": "call_handoff",
                "type": "function",
                "function": {
                    "name": "human_handoff",
                    "arguments": json.dumps(
                        {"brief": "用户要求人工", "reason": "投诉升级"},
                        ensure_ascii=False,
                    ),
                },
            }],
            status="success",
            metadata_={},
        ),
        tool_step,
    ]

    async def fake_get_agent_by_id(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="tenant-a", engine_config={})

    async def fake_get_conversation_by_id(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            external_id="conv_handoff",
            tenant_id="tenant-a",
            agent_id=3,
            source="api",
            round_count=2,
        )

    async def fake_get_tool_call_by_call_id(db, conversation_id, tool_call_id):
        return tool_step

    async def fake_get_steps_by_round(db, conversation_id, round_number):
        return saved_steps

    async def fake_build_history(db, conversation_id, config, current_round):
        return []

    async def fake_load_tools(db, agent_id, selected_tool_ids):
        return []

    async def fake_create_step(db, conversation_id, tenant_id, data):
        item = {**data, "id": len(created_steps) + 100}
        item.setdefault("metadata", {})
        item["metadata_"] = item["metadata"]
        created_steps.append(item)
        return SimpleNamespace(**item)

    async def fake_increment_counters(db, conversation_id, **kwargs):
        counter_updates.append(kwargs)

    @asynccontextmanager
    async def fake_hold_specific_round_lock(db, conversation_id, round_number, **kwargs):
        assert round_number == 3
        yield

    class OneDeltaStream:
        def __init__(self):
            self.done = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.done:
                raise StopAsyncIteration
            self.done = True
            return SimpleNamespace(content="我继续帮你处理。", thinking_content="")

    class FakeLLMClient:
        async def stream_chat(self, messages, **kwargs):
            assert kwargs["tools"] is None
            assert messages[-1] == {
                "role": "tool",
                "tool_call_id": "call_handoff",
                "content": "当前没有可用客服，请继续由机器人处理。",
            }
            return OneDeltaStream(), LLMStreamResult(
                content="我继续帮你处理。",
                thinking_content="",
                tool_calls=[],
                finish_reason="stop",
                model=kwargs.get("model"),
                incomplete_reason=None,
            )

    class FakeDb:
        async def refresh(self, item):
            return None

    monkeypatch.setattr(engine_module.AgentRepository, "get_by_id", fake_get_agent_by_id)
    monkeypatch.setattr(engine_module.ConversationRepository, "get_by_id", fake_get_conversation_by_id)
    monkeypatch.setattr(
        engine_module.ConversationStepRepository,
        "get_tool_call_by_call_id",
        fake_get_tool_call_by_call_id,
    )
    monkeypatch.setattr(
        engine_module.ConversationStepRepository,
        "get_steps_by_round",
        fake_get_steps_by_round,
    )
    monkeypatch.setattr(engine_module, "_build_history", fake_build_history)
    monkeypatch.setattr(engine_module, "_load_tools", fake_load_tools)
    monkeypatch.setattr(engine_module, "_create_step", fake_create_step)
    monkeypatch.setattr(engine_module, "_hold_specific_round_lock", fake_hold_specific_round_lock)
    monkeypatch.setattr(engine_module.ConversationRepository, "increment_counters", fake_increment_counters)
    monkeypatch.setattr(engine_module, "create_llm_client", lambda: FakeLLMClient())

    frames = []
    async for raw in engine_module.AgentEngineService.continue_after_tool_result(
        FakeDb(),
        agent_id=3,
        conversation_id=7,
        tool_call_id="call_handoff",
    ):
        frames.append(raw)

    assert any("event: content_delta\n" in frame for frame in frames)
    assert any("event: done\n" in frame and "handoff_failed" in frame for frame in frames)
    assert [step["step_type"] for step in created_steps] == [
        "llm_call",
        "assistant_message",
    ]
    assert counter_updates and counter_updates[0]["llm_call_count"] == 1


@pytest.mark.asyncio
async def test_failed_handoff_result_skips_continuation_when_newer_round_exists(monkeypatch):
    calls = {}
    tool_step = SimpleNamespace(
        id=55,
        conversation_id=7,
        tenant_id="tenant-a",
        round_number=2,
        step_type="tool_call",
        tool_name="human_handoff",
        tool_type=HUMAN_HANDOFF_TOOL_TYPE,
        tool_call_id="call_handoff",
        tool_arguments={"brief": "用户要求人工", "reason": "投诉升级"},
        tool_response=None,
        brief="用户要求人工",
        status="pending",
        error_message=None,
        metadata_={"tool_config": {}},
    )
    conv = SimpleNamespace(
        id=7,
        external_id="conv_handoff",
        tenant_id="tenant-a",
        agent_id=3,
        source="api",
        round_count=3,
    )

    async def fake_get_agent_by_id(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="tenant-a", engine_config={})

    async def fake_get_conversation_by_id(db, conversation_id):
        return conv

    async def fake_get_tool_call_by_call_id(db, conversation_id, tool_call_id):
        return tool_step

    async def fake_submit_tool_result(db, conversation_id, tenant_id, agent_id, data):
        calls["submitted"] = data.status
        tool_step.status = "error"
        tool_step.tool_response = data.message
        tool_step.error_message = data.message
        return tool_step

    @asynccontextmanager
    async def fake_hold_specific_round_lock(db, conversation_id, round_number, **kwargs):
        calls["lock_round"] = round_number
        yield

    class FakeDb:
        async def refresh(self, item):
            return None

    class FailLLMClient:
        async def stream_chat(self, *args, **kwargs):
            raise AssertionError("newer rounds should suppress failed handoff continuation")

    monkeypatch.setattr(engine_module.AgentRepository, "get_by_id", fake_get_agent_by_id)
    monkeypatch.setattr(engine_module.ConversationRepository, "get_by_id", fake_get_conversation_by_id)
    monkeypatch.setattr(
        engine_module.ConversationStepRepository,
        "get_tool_call_by_call_id",
        fake_get_tool_call_by_call_id,
    )
    monkeypatch.setattr(
        ConversationStepService,
        "submit_tool_result",
        fake_submit_tool_result,
    )
    monkeypatch.setattr(engine_module, "_hold_specific_round_lock", fake_hold_specific_round_lock)
    monkeypatch.setattr(engine_module, "create_llm_client", lambda: FailLLMClient())

    frames = []
    async for raw in engine_module.AgentEngineService.submit_tool_result_stream(
        FakeDb(),
        agent_id=3,
        conversation_id=7,
        tenant_id="tenant-a",
        data=ToolResultSubmit(
            tool_call_id="call_handoff",
            status="handoff_failed",
            message="当前没有可用客服，请继续由机器人处理。",
        ),
    ):
        frames.append(raw)

    assert calls == {"lock_round": 3, "submitted": "handoff_failed"}
    assert any("event: tool_result\n" in frame for frame in frames)
    assert any(
        "event: done\n" in frame and "newer_round_exists" in frame
        for frame in frames
    )


@pytest.mark.asyncio
async def test_human_handoff_event_payload_drops_disabled_route_fields(monkeypatch):
    calls = {}

    async def fake_get_max_step_order(db, conversation_id):
        calls["max_order_conversation_id"] = conversation_id
        return 7

    async def fake_create_step(db, data):
        calls["conversation_id"] = data["conversation_id"]
        calls["tenant_id"] = data["tenant_id"]
        calls["data"] = data
        return SimpleNamespace(id=99, **data)

    monkeypatch.setattr(
        human_handoff_event_service.ConversationStepRepository,
        "get_max_step_order",
        fake_get_max_step_order,
    )
    monkeypatch.setattr(
        human_handoff_event_service.ConversationStepRepository,
        "create",
        fake_create_step,
    )

    await human_handoff_event_service.create_human_handoff_event_step(
        object(),
        SimpleNamespace(id=7, external_id="conv_x", tenant_id="tenant-a"),
        3,
        2,
        SimpleNamespace(id=55),
        {
            "brief": "用户要求人工",
            "reason": "投诉升级",
            "agent_group_id": "group-a",
            "business_type": "complaint",
        },
        {
            "route_fields": {
                "agent_group_id": True,
                "agent_id": False,
                "business_type": False,
            }
        },
    )

    payload = calls["data"]["metadata"]
    assert calls["conversation_id"] == 7
    assert calls["data"]["step_order"] == 8
    assert calls["data"]["step_type"] == "human_handoff_event"
    assert payload["related_tool_call_step_id"] == 55
    assert payload["event_kind"] == "human_handoff"
    assert payload["handoff"]["agent_group_id"] == "group-a"
    assert "business_type" not in payload["handoff"]
