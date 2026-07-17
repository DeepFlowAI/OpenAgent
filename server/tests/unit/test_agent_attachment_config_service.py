"""Unit tests for attachment handoff engine configuration."""

from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.schemas.agent import EngineConfigUpdate
from app.schemas.agent_tool import HUMAN_HANDOFF_TOOL_TYPE
from app.services import agent_service as service_module
from app.services.agent_service import AgentService


@pytest.mark.asyncio
async def test_update_attachment_handoff_tool_accepts_enabled_agent_tool(monkeypatch):
    agent = SimpleNamespace(id=3, engine_config={})
    tool = SimpleNamespace(
        id=9,
        agent_id=3,
        tool_type=HUMAN_HANDOFF_TOOL_TYPE,
        is_enabled=True,
    )
    captured: dict = {}

    async def fake_get_agent(db, agent_id):
        return agent

    async def fake_get_tool(db, tool_id):
        return tool

    async def fake_update(db, item, data):
        captured.update(data)
        return item

    monkeypatch.setattr(
        service_module.AgentRepository,
        "get_by_id",
        fake_get_agent,
    )
    monkeypatch.setattr(
        service_module.AgentToolRepository,
        "get_by_id",
        fake_get_tool,
    )
    monkeypatch.setattr(
        service_module.AgentRepository,
        "update",
        fake_update,
    )

    await AgentService.update_engine_config(
        object(),
        3,
        EngineConfigUpdate(attachment_handoff_tool_id=9),
    )

    assert captured["engine_config"]["attachment_handoff_tool_id"] == 9


@pytest.mark.asyncio
async def test_update_attachment_handoff_tool_rejects_unavailable_tool(monkeypatch):
    agent = SimpleNamespace(id=3, engine_config={})
    tool = SimpleNamespace(
        id=9,
        agent_id=3,
        tool_type=HUMAN_HANDOFF_TOOL_TYPE,
        is_enabled=False,
    )

    async def fake_get_agent(db, agent_id):
        return agent

    async def fake_get_tool(db, tool_id):
        return tool

    monkeypatch.setattr(
        service_module.AgentRepository,
        "get_by_id",
        fake_get_agent,
    )
    monkeypatch.setattr(
        service_module.AgentToolRepository,
        "get_by_id",
        fake_get_tool,
    )

    with pytest.raises(ValidationError, match="enabled human handoff"):
        await AgentService.update_engine_config(
            object(),
            3,
            EngineConfigUpdate(attachment_handoff_tool_id=9),
        )


@pytest.mark.asyncio
async def test_clear_attachment_handoff_tool_does_not_lookup_tool(monkeypatch):
    agent = SimpleNamespace(id=3, engine_config={"attachment_handoff_tool_id": 9})
    captured: dict = {}

    async def fake_get_agent(db, agent_id):
        return agent

    async def fail_get_tool(db, tool_id):
        raise AssertionError("Clearing the setting must not look up a tool")

    async def fake_update(db, item, data):
        captured.update(data)
        return item

    monkeypatch.setattr(
        service_module.AgentRepository,
        "get_by_id",
        fake_get_agent,
    )
    monkeypatch.setattr(
        service_module.AgentToolRepository,
        "get_by_id",
        fail_get_tool,
    )
    monkeypatch.setattr(
        service_module.AgentRepository,
        "update",
        fake_update,
    )

    await AgentService.update_engine_config(
        object(),
        3,
        EngineConfigUpdate(attachment_handoff_tool_id=None),
    )

    assert captured["engine_config"]["attachment_handoff_tool_id"] is None
