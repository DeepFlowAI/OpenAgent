"""
Unit tests for the conversation title summary service.

The actual LLM call is mocked — we never hit the external (token-billed) API.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import conversation_title_service as svc


class _FakeSessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


def _patch_session(monkeypatch):
    db = object()
    monkeypatch.setattr(svc, "AsyncSessionLocal", lambda: _FakeSessionCtx(db))
    return db


def _patch_llm(monkeypatch, content: str):
    client = SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(content=content)))
    monkeypatch.setattr(svc, "create_llm_client", lambda: client)
    return client


# ── _clean_title ────────────────────────────────────────────────────────────

class TestCleanTitle:
    def test_strips_quotes_and_trailing_punctuation(self):
        assert svc._clean_title('"退款流程咨询。"', 15) == "退款流程咨询"

    def test_keeps_only_first_line(self):
        assert svc._clean_title("订单状态查询\n额外说明", 15) == "订单状态查询"

    def test_truncates_to_max_chars(self):
        assert svc._clean_title("一二三四五六七八九十", 4) == "一二三四"

    def test_empty_input_returns_empty(self):
        assert svc._clean_title("", 15) == ""
        assert svc._clean_title("   ", 15) == ""


# ── _should_overwrite ─────────────────────────────────────────────────────────

class TestShouldOverwrite:
    def test_overwrites_empty_title(self):
        assert svc._should_overwrite(None, "fallback") is True
        assert svc._should_overwrite("", "fallback") is True

    def test_overwrites_fallback_title(self):
        assert svc._should_overwrite("如何退款", "如何退款") is True

    def test_skips_preset_title(self):
        assert svc._should_overwrite("VIP 客户预置标题", "如何退款") is False


# ── _generate_and_store ───────────────────────────────────────────────────────

class TestGenerateAndStore:
    @pytest.mark.asyncio
    async def test_writes_summary_when_title_is_fallback(self, monkeypatch):
        _patch_session(monkeypatch)
        _patch_llm(monkeypatch, "退款流程咨询")
        conv = SimpleNamespace(title="我想申请退款怎么操作")
        monkeypatch.setattr(
            svc.ConversationRepository, "get_by_id", AsyncMock(return_value=conv)
        )
        update = AsyncMock(return_value=True)
        monkeypatch.setattr(
            svc.ConversationRepository, "update_title_if_overwritable", update
        )

        await svc._generate_and_store(1, "我想申请退款怎么操作", "请提供订单号")

        update.assert_called_once()
        # Atomic conditional update: (db, conversation_id, new_title, fallback).
        assert update.call_args.args[1] == 1
        assert update.call_args.args[2] == "退款流程咨询"
        assert update.call_args.args[3] == "我想申请退款怎么操作"

    @pytest.mark.asyncio
    async def test_skips_when_title_is_preset(self, monkeypatch):
        _patch_session(monkeypatch)
        _patch_llm(monkeypatch, "退款流程咨询")
        conv = SimpleNamespace(title="VIP 预置标题")
        monkeypatch.setattr(
            svc.ConversationRepository, "get_by_id", AsyncMock(return_value=conv)
        )
        update = AsyncMock(return_value=True)
        monkeypatch.setattr(
            svc.ConversationRepository, "update_title_if_overwritable", update
        )

        await svc._generate_and_store(1, "我想申请退款怎么操作", "请提供订单号")

        update.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_summary_is_empty(self, monkeypatch):
        _patch_session(monkeypatch)
        _patch_llm(monkeypatch, "   ")
        conv = SimpleNamespace(title=None)
        monkeypatch.setattr(
            svc.ConversationRepository, "get_by_id", AsyncMock(return_value=conv)
        )
        update = AsyncMock(return_value=True)
        monkeypatch.setattr(
            svc.ConversationRepository, "update_title_if_overwritable", update
        )

        await svc._generate_and_store(1, "你好", "你好，有什么可以帮你")

        update.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_failure_is_swallowed(self, monkeypatch):
        _patch_session(monkeypatch)
        client = SimpleNamespace(chat=AsyncMock(side_effect=RuntimeError("boom")))
        monkeypatch.setattr(svc, "create_llm_client", lambda: client)
        conv = SimpleNamespace(title=None)
        monkeypatch.setattr(
            svc.ConversationRepository, "get_by_id", AsyncMock(return_value=conv)
        )
        update = AsyncMock(return_value=True)
        monkeypatch.setattr(
            svc.ConversationRepository, "update_title_if_overwritable", update
        )

        # Must not raise.
        await svc._generate_and_store(1, "你好", "你好，有什么可以帮你")

        update.assert_not_called()


# ── schedule_title_summary ────────────────────────────────────────────────────

class TestScheduleTitleSummary:
    def test_disabled_flag_does_not_schedule(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "CONVERSATION_TITLE_ENABLED", False)
        called = False

        def _fake_create_task(coro):
            nonlocal called
            called = True
            coro.close()

        monkeypatch.setattr(svc.asyncio, "create_task", _fake_create_task)
        svc.schedule_title_summary(1, "hi", "hello")
        assert called is False

    def test_missing_args_do_not_schedule(self, monkeypatch):
        monkeypatch.setattr(svc.settings, "CONVERSATION_TITLE_ENABLED", True)
        called = False

        def _fake_create_task(coro):
            nonlocal called
            called = True
            coro.close()

        monkeypatch.setattr(svc.asyncio, "create_task", _fake_create_task)
        svc.schedule_title_summary(0, "hi", "hello")
        svc.schedule_title_summary(1, "", "hello")
        svc.schedule_title_summary(1, "hi", "")
        assert called is False
