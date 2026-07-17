"""Unit tests for deterministic Open API attachment handling."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.schemas.agent_tool import HUMAN_HANDOFF_TOOL_TYPE
from app.schemas.conversation_step import ToolResultSubmit
from app.services import agent_engine_service as engine_module
from app.services import human_handoff_event_service as event_module
from app.services import conversation_step_service as step_service_module
from app.services.conversation_step_service import ConversationStepService


ATTACHMENTS = [
    {
        "type": "image",
        "url": "https://files.example.com/photo.png?token=secret",
        "name": "photo.png",
        "mime_type": "image/png",
        "size": 128,
    }
]


def _event_payload(frame: str) -> dict:
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


def test_normalize_attachment_message_appends_urls_in_order():
    attachments = [
        {**ATTACHMENTS[0], "url": "https://files.example.com/1.png"},
        {**ATTACHMENTS[0], "url": "https://files.example.com/2.png"},
    ]

    assert engine_module._normalize_attachment_message("原文", attachments) == (
        "原文\nhttps://files.example.com/1.png\nhttps://files.example.com/2.png"
    )
    assert engine_module._normalize_attachment_message("", attachments) == (
        "https://files.example.com/1.png\nhttps://files.example.com/2.png"
    )


@pytest.mark.asyncio
async def test_configured_attachment_creates_pending_handoff_without_llm(monkeypatch):
    created_steps: list[dict] = []
    counter_updates: list[dict] = []

    async def fake_get_agent(db, agent_id):
        return SimpleNamespace(
            id=agent_id,
            tenant_id="tenant-a",
            engine_config={"attachment_handoff_tool_id": 9},
        )

    async def fake_get_conversation(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="tenant-a",
            agent_id=3,
            round_count=0,
            title="已有标题",
            external_id="conv_attachment",
            source="api",
        )

    @asynccontextmanager
    async def fake_hold_round_lock(
        db, conv, conversation_id, client_message_id, **kwargs
    ):
        yield 1, False

    async def fake_create_step(db, conversation_id, tenant_id, data):
        item = {**data, "id": len(created_steps) + 1}
        item.setdefault("metadata", {})
        item["metadata_"] = item["metadata"]
        created_steps.append(item)
        return SimpleNamespace(**item)

    async def fake_load_attachment_tool(db, agent_id, tenant_id, tool_id):
        return {
            "id": tool_id,
            "name": "human_handoff",
            "description": "Request human support.",
            "parameters_schema": {},
            "tool_type": HUMAN_HANDOFF_TOOL_TYPE,
            "config": {},
        }

    async def fake_increment_counters(db, conversation_id, **kwargs):
        counter_updates.append(kwargs)

    monkeypatch.setattr(engine_module.AgentRepository, "get_by_id", fake_get_agent)
    monkeypatch.setattr(
        engine_module.ConversationRepository,
        "get_by_id",
        fake_get_conversation,
    )
    monkeypatch.setattr(engine_module, "_hold_round_lock", fake_hold_round_lock)
    monkeypatch.setattr(engine_module, "_create_step", fake_create_step)
    monkeypatch.setattr(
        engine_module,
        "_load_attachment_handoff_tool",
        fake_load_attachment_tool,
    )
    monkeypatch.setattr(
        engine_module.ConversationRepository,
        "increment_counters",
        fake_increment_counters,
    )
    monkeypatch.setattr(
        engine_module,
        "create_llm_client",
        lambda: (_ for _ in ()).throw(AssertionError("LLM must not be created")),
    )

    frames = []
    async for frame in engine_module.AgentEngineService._run_chat_round_impl(
        db=SimpleNamespace(),
        agent_id=3,
        user_message="请人工处理",
        conversation_id=7,
        client_message_id="msg-attachment-1",
        attachments=ATTACHMENTS,
    ):
        frames.append(frame)

    assert [step["step_type"] for step in created_steps] == [
        "user_message",
        "tool_call",
    ]
    assert created_steps[0]["content"] == "请人工处理"
    assert created_steps[0]["metadata"]["attachments"] == ATTACHMENTS
    assert created_steps[1]["status"] == "pending"
    assert created_steps[1]["tool_arguments"]["attachments"] == ATTACHMENTS
    assert created_steps[1]["parent_step_id"] == created_steps[0]["id"]
    assert counter_updates == [{"tool_call_count": 1, "round_count": 1}]

    action_frame = next(
        frame for frame in frames if "\nevent: requires_action\n" in frame
    )
    action = _event_payload(action_frame)
    assert action["user_message"] == "请人工处理"
    assert action["attachments"] == ATTACHMENTS
    assert any("tool_result_required" in frame for frame in frames)


@pytest.mark.asyncio
async def test_unavailable_configured_tool_fails_before_message_or_llm(monkeypatch):
    created_steps: list[dict] = []

    async def fake_get_agent(db, agent_id):
        return SimpleNamespace(
            id=agent_id,
            tenant_id="tenant-a",
            engine_config={"attachment_handoff_tool_id": 9},
        )

    async def fake_get_conversation(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="tenant-a",
            agent_id=3,
            round_count=0,
            title="已有标题",
            external_id="conv_attachment",
            source="api",
        )

    @asynccontextmanager
    async def fake_hold_round_lock(
        db, conv, conversation_id, client_message_id, **kwargs
    ):
        yield 1, False

    async def fail_load_tool(db, agent_id, tenant_id, tool_id):
        raise ValidationError("当前无法处理图片或文件消息，请检查转人工工具设置")

    async def fake_create_step(db, conversation_id, tenant_id, data):
        created_steps.append(data)

    monkeypatch.setattr(engine_module.AgentRepository, "get_by_id", fake_get_agent)
    monkeypatch.setattr(
        engine_module.ConversationRepository,
        "get_by_id",
        fake_get_conversation,
    )
    monkeypatch.setattr(engine_module, "_hold_round_lock", fake_hold_round_lock)
    monkeypatch.setattr(
        engine_module, "_load_attachment_handoff_tool", fail_load_tool
    )
    monkeypatch.setattr(engine_module, "_create_step", fake_create_step)
    monkeypatch.setattr(
        engine_module,
        "create_llm_client",
        lambda: (_ for _ in ()).throw(AssertionError("LLM must not be created")),
    )

    with pytest.raises(ValidationError, match="当前无法处理"):
        async for _frame in engine_module.AgentEngineService._run_chat_round_impl(
            db=SimpleNamespace(),
            agent_id=3,
            user_message="",
            conversation_id=7,
            attachments=ATTACHMENTS,
        ):
            pass

    assert created_steps == []


@pytest.mark.asyncio
async def test_attachment_rejects_non_api_conversation_source(monkeypatch):
    async def fake_get_agent(db, agent_id):
        return SimpleNamespace(id=agent_id, tenant_id="tenant-a", engine_config={})

    async def fake_get_conversation(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="tenant-a",
            agent_id=3,
            round_count=0,
            title="已有标题",
            external_id="conv_websdk",
            source="websdk",
        )

    monkeypatch.setattr(engine_module.AgentRepository, "get_by_id", fake_get_agent)
    monkeypatch.setattr(
        engine_module.ConversationRepository,
        "get_by_id",
        fake_get_conversation,
    )

    with pytest.raises(ValidationError, match="only supported for API conversations"):
        async for _frame in engine_module.AgentEngineService._run_chat_round_impl(
            db=SimpleNamespace(),
            agent_id=3,
            user_message="",
            conversation_id=7,
            attachments=ATTACHMENTS,
        ):
            pass


@pytest.mark.asyncio
async def test_handoff_event_copies_attachment_snapshot(monkeypatch):
    captured: dict = {}

    async def fake_get_max_order(db, conversation_id):
        return 2

    async def fake_create(db, data):
        captured.update(data)
        return SimpleNamespace(**data, id=3)

    monkeypatch.setattr(
        event_module.ConversationStepRepository,
        "get_max_step_order",
        fake_get_max_order,
    )
    monkeypatch.setattr(
        event_module.ConversationStepRepository,
        "create",
        fake_create,
    )

    await event_module.create_human_handoff_event_step(
        object(),
        SimpleNamespace(
            id=7,
            external_id="conv_attachment",
            tenant_id="tenant-a",
        ),
        3,
        1,
        SimpleNamespace(id=2),
        {
            "brief": "用户发送图片或文件，需要人工处理",
            "reason": "用户消息包含图片或文件附件",
            "user_message": "请人工处理",
            "attachments": ATTACHMENTS,
        },
        {},
    )

    assert captured["metadata"]["attachments"] == ATTACHMENTS
    assert captured["metadata"]["user_message"] == "请人工处理"


@pytest.mark.asyncio
async def test_repeated_success_tool_result_is_idempotent(monkeypatch):
    tool_step = SimpleNamespace(
        id=55,
        tool_type=HUMAN_HANDOFF_TOOL_TYPE,
        status="success",
    )

    async def fake_get_conversation(db, conversation_id):
        return SimpleNamespace(
            id=conversation_id,
            tenant_id="tenant-a",
            agent_id=3,
        )

    async def fake_get_tool_call(db, conversation_id, tool_call_id):
        return tool_step

    async def fail_update(*args, **kwargs):
        raise AssertionError("Repeated result must not update the step")

    monkeypatch.setattr(
        step_service_module.ConversationRepository,
        "get_by_id",
        fake_get_conversation,
    )
    monkeypatch.setattr(
        step_service_module.ConversationStepRepository,
        "get_tool_call_by_call_id",
        fake_get_tool_call,
    )
    monkeypatch.setattr(
        step_service_module.ConversationStepRepository,
        "update",
        fail_update,
    )

    result = await ConversationStepService.submit_tool_result(
        object(),
        7,
        "tenant-a",
        3,
        ToolResultSubmit(
            tool_call_id="attachment_handoff_1",
            status="handoff_success",
            message="accepted",
        ),
    )

    assert result is tool_step


@pytest.mark.asyncio
async def test_failed_attachment_handoff_does_not_continue_to_llm(monkeypatch):
    tool_step = SimpleNamespace(
        id=55,
        round_number=1,
        tool_call_id="attachment_handoff_1",
        tool_response="queue rejected",
        tool_type=HUMAN_HANDOFF_TOOL_TYPE,
        status="pending",
        metadata_={"attachment_auto_handoff": True},
    )
    agent = SimpleNamespace(id=3, tenant_id="tenant-a")
    conversation = SimpleNamespace(
        id=7,
        tenant_id="tenant-a",
        agent_id=3,
        round_count=1,
    )

    async def fake_get_agent(db, agent_id):
        return agent

    async def fake_get_conversation(db, conversation_id):
        return conversation

    async def fake_get_tool_call(db, conversation_id, tool_call_id):
        return tool_step

    @asynccontextmanager
    async def fake_hold_lock(db, conversation_id, round_number, **kwargs):
        yield

    async def fake_submit_result(db, conversation_id, tenant_id, agent_id, data):
        tool_step.status = "error"
        return tool_step

    async def fail_continue(*args, **kwargs):
        raise AssertionError("Attachment handoff failure must not continue to LLM")
        yield

    class FakeDb:
        async def refresh(self, item):
            return None

    monkeypatch.setattr(engine_module.AgentRepository, "get_by_id", fake_get_agent)
    monkeypatch.setattr(
        engine_module.ConversationRepository,
        "get_by_id",
        fake_get_conversation,
    )
    monkeypatch.setattr(
        engine_module.ConversationStepRepository,
        "get_tool_call_by_call_id",
        fake_get_tool_call,
    )
    monkeypatch.setattr(engine_module, "_hold_specific_round_lock", fake_hold_lock)
    monkeypatch.setattr(
        step_service_module.ConversationStepService,
        "submit_tool_result",
        fake_submit_result,
    )
    monkeypatch.setattr(
        engine_module,
        "_continue_after_failed_tool_result",
        fail_continue,
    )

    frames = []
    async for frame in engine_module.AgentEngineService._submit_tool_result_stream_impl(
        FakeDb(),
        agent_id=3,
        conversation_id=7,
        tenant_id="tenant-a",
        data=ToolResultSubmit(
            tool_call_id="attachment_handoff_1",
            status="handoff_failed",
            message="queue rejected",
        ),
    ):
        frames.append(frame)

    assert any("handoff_failed" in frame for frame in frames)
