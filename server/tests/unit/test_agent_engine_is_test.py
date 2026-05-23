"""
Unit tests for conversation test-flag creation in the agent engine.
"""
from types import SimpleNamespace

import pytest

from app.services.agent_engine_service import AgentEngineService


class TestAgentEngineIsTest:
    @pytest.mark.asyncio
    async def test_new_conversation_copies_is_test_without_changing_source(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict = {}

        async def fake_get_agent_by_id(db, agent_id):
            return SimpleNamespace(id=agent_id, tenant_id="T_TEST", engine_config={})

        async def fake_create_conversation(db, data):
            captured.update(data)
            return SimpleNamespace(id=123, external_id="conv_test")

        monkeypatch.setattr(
            "app.services.agent_engine_service.AgentRepository.get_by_id",
            fake_get_agent_by_id,
        )
        monkeypatch.setattr(
            "app.services.agent_engine_service.ConversationRepository.create",
            fake_create_conversation,
        )

        stream = AgentEngineService._run_chat_round_impl(
            db=SimpleNamespace(),
            agent_id=1,
            user_message="hello",
            conversation_id=None,
            customer_context={"source": "testchat", "is_test": True},
        )
        event = await anext(stream)
        await stream.aclose()

        assert captured["is_test"] is True
        assert captured["source"] == "testchat"
        assert "is_test" not in event

    @pytest.mark.asyncio
    async def test_new_conversation_copies_valid_channel_source(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict = {}

        async def fake_get_agent_by_id(db, agent_id):
            return SimpleNamespace(id=agent_id, tenant_id="T_TEST", engine_config={})

        async def fake_create_conversation(db, data):
            captured.update(data)
            return SimpleNamespace(id=123, external_id="conv_test")

        monkeypatch.setattr(
            "app.services.agent_engine_service.AgentRepository.get_by_id",
            fake_get_agent_by_id,
        )
        monkeypatch.setattr(
            "app.services.agent_engine_service.ConversationRepository.create",
            fake_create_conversation,
        )

        stream = AgentEngineService._run_chat_round_impl(
            db=SimpleNamespace(),
            agent_id=1,
            user_message="hello",
            conversation_id=None,
            customer_context={
                "source": "websdk",
                "channel_id": 11,
                "channel_source": " official_site ",
            },
        )
        await anext(stream)
        await stream.aclose()

        assert captured["channel_source"] == "official_site"
        assert captured["channel_id"] == 11
        assert captured["source"] == "websdk"

    @pytest.mark.asyncio
    async def test_new_conversation_drops_invalid_channel_source(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        captured: dict = {}

        async def fake_get_agent_by_id(db, agent_id):
            return SimpleNamespace(id=agent_id, tenant_id="T_TEST", engine_config={})

        async def fake_create_conversation(db, data):
            captured.update(data)
            return SimpleNamespace(id=123, external_id="conv_test")

        monkeypatch.setattr(
            "app.services.agent_engine_service.AgentRepository.get_by_id",
            fake_get_agent_by_id,
        )
        monkeypatch.setattr(
            "app.services.agent_engine_service.ConversationRepository.create",
            fake_create_conversation,
        )

        stream = AgentEngineService._run_chat_round_impl(
            db=SimpleNamespace(),
            agent_id=1,
            user_message="hello",
            conversation_id=None,
            customer_context={"channel_source": "official\nsite"},
        )
        await anext(stream)
        await stream.aclose()

        assert "channel_source" not in captured
