"""
Unit tests for channel_source normalization.
"""
import pytest

from app.schemas.conversation import (
    ConversationCreate,
    normalize_channel_source,
    normalize_conversation_source,
)
from app.services.conversation_service import ConversationService


def test_normalize_channel_source_trims_valid_value():
    assert normalize_channel_source("  official_site  ") == "official_site"


def test_normalize_channel_source_ignores_empty_value():
    assert normalize_channel_source("   ") is None


def test_normalize_channel_source_ignores_too_long_value():
    assert normalize_channel_source("a" * 65) is None


def test_normalize_channel_source_ignores_control_characters():
    assert normalize_channel_source("official\nsite") is None
    assert normalize_channel_source("official\tsite") is None


def test_normalize_channel_source_counts_unicode_characters():
    assert normalize_channel_source("入口" * 32) == "入口" * 32
    assert normalize_channel_source("入口" * 33) is None


def test_normalize_conversation_source_accepts_target_values():
    assert normalize_conversation_source("websdk") == "websdk"
    assert normalize_conversation_source("api") == "api"
    assert normalize_conversation_source("testchat") == "testchat"


def test_normalize_conversation_source_maps_legacy_values():
    assert normalize_conversation_source("chat") == "websdk"
    assert normalize_conversation_source("embed") == "websdk"
    assert normalize_conversation_source("SDK_test") == "testchat"


def test_normalize_conversation_source_rejects_unknown_value():
    with pytest.raises(ValueError):
        normalize_conversation_source("unknown")


async def test_conversation_service_create_normalizes_channel_source(monkeypatch):
    captured: dict = {}

    async def fake_create(db, data):
        captured.update(data)
        return data

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.create",
        fake_create,
    )

    payload = ConversationCreate(
        tenant_id="T_TEST",
        agent_id=1,
        channel_source=" official_site ",
    )

    await ConversationService.create(db=None, data=payload)

    assert captured["channel_source"] == "official_site"


async def test_conversation_service_create_drops_invalid_channel_source(monkeypatch):
    captured: dict = {}

    async def fake_create(db, data):
        captured.update(data)
        return data

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.create",
        fake_create,
    )

    payload = ConversationCreate(
        tenant_id="T_TEST",
        agent_id=1,
        channel_source="bad\tsource",
    )

    await ConversationService.create(db=None, data=payload)

    assert "channel_source" not in captured


async def test_conversation_service_create_returns_channel_name(monkeypatch):
    captured: dict = {}

    async def fake_get_names_by_ids(db, tenant_id, channel_ids):
        assert tenant_id == "T_TEST"
        assert channel_ids == [42]
        return {42: "官网 WebSDK"}

    async def fake_create(db, data):
        captured.update(data)
        return data

    monkeypatch.setattr(
        "app.services.conversation_service.ChannelRepository.get_names_by_ids",
        fake_get_names_by_ids,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.create",
        fake_create,
    )

    payload = ConversationCreate(
        tenant_id="T_TEST",
        agent_id=1,
        source="websdk",
        channel_id=42,
    )

    result = await ConversationService.create(db=None, data=payload)

    assert captured["channel_id"] == 42
    assert result["channel_name"] == "官网 WebSDK"


async def test_conversation_service_get_paginated_filters_multiple_sources(monkeypatch):
    captured: dict = {}

    async def fake_get_paginated(db, tenant_id, agent_id, **kwargs):
        captured.update(kwargs)
        return [], 0

    async def fake_get_names_by_ids(db, tenant_id, channel_ids):
        return {}

    monkeypatch.setattr(
        "app.services.conversation_service.ConversationRepository.get_paginated",
        fake_get_paginated,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ChannelRepository.get_names_by_ids",
        fake_get_names_by_ids,
    )

    await ConversationService.get_paginated(
        db=None,
        tenant_id="T_TEST",
        agent_id=1,
        source="websdk,testchat,chat",
    )

    assert captured["source"] == ["websdk", "testchat"]
