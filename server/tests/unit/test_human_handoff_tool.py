"""
Unit tests for the human handoff system tool.
"""
from types import SimpleNamespace
from datetime import datetime

import pytest

from app.core.exceptions import ValidationError
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
from app.services import agent_engine_service as engine_module
from app.services.agent_tool_service import AgentToolService
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
async def test_human_handoff_executor_validates_conversation_and_arguments(monkeypatch):
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

    assert 'status="recorded"' in result
    assert "do not claim that a human agent has joined" in result


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
async def test_human_handoff_event_payload_drops_disabled_route_fields(monkeypatch):
    calls = {}

    async def fake_create_step(db, conversation_id, tenant_id, data):
        calls["conversation_id"] = conversation_id
        calls["tenant_id"] = tenant_id
        calls["data"] = data
        return SimpleNamespace(id=99, **data)

    monkeypatch.setattr(engine_module, "_create_step", fake_create_step)

    await engine_module._create_human_handoff_event_step(
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
            "tool_type": HUMAN_HANDOFF_TOOL_TYPE,
            "config": {
                "route_fields": {
                    "agent_group_id": True,
                    "agent_id": False,
                    "business_type": False,
                }
            },
        },
        '<human_handoff_response status="recorded"></human_handoff_response>',
    )

    payload = calls["data"]["metadata"]
    assert calls["conversation_id"] == 7
    assert calls["data"]["step_type"] == "human_handoff_event"
    assert payload["related_tool_call_step_id"] == 55
    assert payload["event_kind"] == "human_handoff"
    assert payload["handoff"]["agent_group_id"] == "group-a"
    assert "business_type" not in payload["handoff"]
