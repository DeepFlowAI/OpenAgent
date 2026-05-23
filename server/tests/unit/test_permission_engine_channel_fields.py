"""
Unit tests for permission engine channel system fields.
"""
from types import SimpleNamespace

from app.services.permission_engine import _build_eval_fields, _evaluate_user_conditions
from app.services.tool_executors.search_executor import _load_subject_context


def test_system_channel_fields_are_namespaced_and_match_conditions():
    eval_fields = _build_eval_fields({
        "source": "websdk",
        "channel_id": 42,
        "channel_source": "official_site",
        "metadata": {"source": "metadata_source"},
    })

    assert eval_fields["source"] == "metadata_source"
    assert eval_fields["system.source"] == "websdk"
    assert eval_fields["system.channel_id"] == 42
    assert eval_fields["system.channel_source"] == "official_site"

    assert _evaluate_user_conditions([
        {"field": "system.source", "operator": "equals", "value": "websdk"},
        {"field": "system.channel_id", "operator": "equals", "value": "42"},
        {
            "field": "system.channel_source",
            "operator": "equals",
            "value": "official_site",
        },
    ], eval_fields)


def test_source_legacy_values_are_empty_for_permission_eval():
    eval_fields = _build_eval_fields({
        "source": "chat",
        "metadata": {},
    })

    assert eval_fields["system.source"] is None
    assert _evaluate_user_conditions([
        {"field": "system.source", "operator": "is_empty", "value": None},
    ], eval_fields)


def test_invalid_channel_source_is_empty_for_permission_eval():
    eval_fields = _build_eval_fields({
        "channel_source": "bad\tsource",
        "metadata": {},
    })

    assert eval_fields["system.channel_source"] is None
    assert _evaluate_user_conditions([
        {"field": "system.channel_source", "operator": "is_empty", "value": None},
    ], eval_fields)


def test_legacy_channel_field_uses_channel_id_when_metadata_has_no_channel():
    eval_fields = _build_eval_fields({
        "channel_id": 42,
        "metadata": {},
    })

    assert eval_fields["channel"] == 42
    assert _evaluate_user_conditions([
        {"field": "channel", "operator": "equals", "value": "42"},
    ], eval_fields)


def test_legacy_channel_field_does_not_override_metadata_channel():
    eval_fields = _build_eval_fields({
        "channel_id": 42,
        "metadata": {"channel": "metadata_channel"},
    })

    assert eval_fields["channel"] == "metadata_channel"
    assert not _evaluate_user_conditions([
        {"field": "channel", "operator": "equals", "value": "42"},
    ], eval_fields)


async def test_load_subject_context_includes_channel_fields(monkeypatch):
    async def fake_get_by_id(db, conversation_id):
        assert conversation_id == 7
        return SimpleNamespace(
            external_user_id="member-1",
            display_name="Member",
            email="member@example.com",
            source="websdk",
            channel_id=42,
            channel_source="official_site",
            metadata_={"tier": "vip"},
        )

    monkeypatch.setattr(
        "app.repositories.conversation_repository.ConversationRepository.get_by_id",
        fake_get_by_id,
    )

    subject = await _load_subject_context(
        SimpleNamespace(db=None, conversation_id=7)
    )

    assert subject == {
        "external_user_id": "member-1",
        "display_name": "Member",
        "email": "member@example.com",
        "source": "websdk",
        "channel_id": 42,
        "channel_source": "official_site",
        "metadata": {"tier": "vip"},
    }
