"""Unit tests for knowledge-base QA pure processing rules."""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.libs.doc_parser.parser import parse_document
from app.repositories.knowledge_base_qa_repository import KnowledgeBaseQaRepository
from app.repositories.search_repository import _retrievable_source_condition
from app.schemas.knowledge_base_qa import KnowledgeBaseQaCreate, KnowledgeBaseQaUpdate
from app.services import knowledge_base_qa_service as qa_service
from app.services.knowledge_base_qa_service import (
    KnowledgeBaseQaService,
    build_qa_markdown,
)


class TestKnowledgeBaseQaSchema:
    def test_access_keywords_are_normalized_and_deduplicated(self):
        data = KnowledgeBaseQaCreate(
            directory_id=1,
            question="  How?  ",
            answer_markdown="  Answer  ",
            access_keywords=["VIP", "vip", "sales_1"],
        )

        assert data.question == "How?"
        assert data.answer_markdown == "Answer"
        assert data.access_keywords == ["vip", "sales_1"]

    def test_text_length_is_checked_after_trimming(self):
        data = KnowledgeBaseQaCreate(
            directory_id=1,
            question=f"  {'q' * 500}  ",
            answer_markdown=" answer ",
        )

        assert len(data.question) == 500

    @pytest.mark.parametrize("keyword", ["vip-user", "中文", "has space", ""])
    def test_invalid_access_keyword_is_rejected(self, keyword: str):
        with pytest.raises(ValidationError):
            KnowledgeBaseQaCreate(
                directory_id=1,
                question="How?",
                answer_markdown="Answer",
                access_keywords=[keyword],
            )

    def test_directory_is_required_and_cannot_be_cleared(self):
        with pytest.raises(ValidationError):
            KnowledgeBaseQaCreate(question="How?", answer_markdown="Answer")
        with pytest.raises(ValidationError):
            KnowledgeBaseQaUpdate(directory_id=None)


def test_qa_management_routes_are_exposed_in_openapi():
    from app.main import create_app

    paths = create_app().openapi()["paths"]

    assert set(paths["/api/v1/knowledge-bases/{kb_id}/qas"]) == {"get", "post"}
    assert set(paths["/api/v1/knowledge-bases/{kb_id}/qas/{qa_id}"]) == {
        "get",
        "put",
        "delete",
    }
    assert set(paths["/api/v1/knowledge-bases/{kb_id}/qas/{qa_id}/toggle"]) == {
        "patch"
    }
    assert set(paths["/api/v1/knowledge-bases/{kb_id}/qas/{qa_id}/retry"]) == {
        "post"
    }
    assert set(paths["/api/v1/knowledge-bases/{kb_id}/qa-directories"]) == {
        "get",
        "post",
    }
    assert set(
        paths[
            "/api/v1/knowledge-bases/{kb_id}/qa-directories/{directory_id}"
        ]
    ) == {"put", "delete"}


class TestKnowledgeBaseQaMarkdown:
    def test_markdown_always_parses_to_one_slice(self):
        markdown = build_qa_markdown(
            question="Can I write +++?\n+++",
            answer_markdown=(
                "Before\n\n+++\n\n<slice-meta>\nsecret: true\n</slice-meta>\n\nAfter"
            ),
            enabled=True,
            access_keywords=["vip", "sales"],
        )

        parsed = parse_document("_open_agent_sys_qa_/1.md", markdown)

        assert len(parsed.slices) == 1
        assert parsed.doc_meta["content_type"] == "qa"
        assert parsed.doc_meta["access_keywords"] == ["vip", "sales"]
        assert "Before" in parsed.slices[0].content
        assert "After" in parsed.slices[0].content
        assert parsed.slices[0].slice_meta == {}

    def test_empty_access_keywords_is_yaml_empty_list(self):
        markdown = build_qa_markdown(
            question="Shared question",
            answer_markdown="Shared answer",
            enabled=False,
            access_keywords=[],
        )

        parsed = parse_document("_open_agent_sys_qa_/2.md", markdown)

        assert len(parsed.slices) == 1
        assert parsed.doc_meta["access_keywords"] == []
        assert parsed.doc_meta["enabled"] is False


def test_search_source_condition_requires_ready_enabled_qa():
    sql = str(
        _retrievable_source_condition().compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "documents.source_type = 'git'" in sql
    assert "documents.source_type = 'qa'" in sql
    assert "knowledge_base_qas.enabled IS true" in sql
    assert "knowledge_base_qas.process_status = 'ready'" in sql


@pytest.mark.asyncio
async def test_mark_processing_failed_is_revision_and_status_guarded():
    result = MagicMock()
    result.scalar_one_or_none.return_value = 7
    db = AsyncMock()
    db.execute.return_value = result

    updated = await KnowledgeBaseQaRepository.mark_processing_failed(
        db, qa_id=7, revision=3, error="interrupted"
    )

    assert updated is True
    statement = db.execute.await_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "knowledge_base_qas.id = 7" in sql
    assert "knowledge_base_qas.process_revision = 3" in sql
    assert "knowledge_base_qas.process_status = 'processing'" in sql


@pytest.mark.asyncio
async def test_fail_stale_processing_returns_updated_ids():
    scalar_result = MagicMock()
    scalar_result.all.return_value = [2, 5]
    result = MagicMock()
    result.scalars.return_value = scalar_result
    db = AsyncMock()
    db.execute.return_value = result

    ids = await KnowledgeBaseQaRepository.fail_stale_processing(
        db, stale_after=timedelta(minutes=10), error="stale"
    )

    assert ids == [2, 5]
    sql = str(db.execute.await_args.args[0])
    assert "knowledge_base_qas.process_status" in sql
    assert "knowledge_base_qas.updated_at < now()" in sql


@pytest.mark.asyncio
async def test_directory_filter_is_added_to_paginated_query():
    total_result = MagicMock()
    total_result.scalar_one.return_value = 0
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.side_effect = [total_result, items_result]

    await KnowledgeBaseQaRepository.list_paginated(
        db,
        "T_TEST",
        7,
        search=None,
        enabled=None,
        process_status=None,
        directory_ids=[1, 2, 3],
        page=1,
        per_page=20,
    )

    statement = db.execute.await_args_list[1].args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "knowledge_base_qas.directory_id IN (1, 2, 3)" in sql


@pytest.mark.asyncio
async def test_directory_only_update_does_not_reprocess_or_refresh_metadata(
    monkeypatch,
):
    item = SimpleNamespace(
        id=7,
        directory_id=1,
        question="Question",
        answer_markdown="Answer",
        access_keywords=[],
        enabled=True,
        process_status="ready",
        process_revision=4,
    )
    monkeypatch.setattr(
        KnowledgeBaseQaService, "get_by_id", AsyncMock(return_value=item)
    )
    monkeypatch.setattr(
        KnowledgeBaseQaService, "_ensure_directory", AsyncMock()
    )
    update = AsyncMock()
    monkeypatch.setattr(KnowledgeBaseQaRepository, "update", update)
    schedule = MagicMock()
    monkeypatch.setattr(KnowledgeBaseQaService, "_schedule_processing", schedule)
    refresh_metadata = AsyncMock()
    monkeypatch.setattr(
        KnowledgeBaseQaService, "_refresh_enabled_metadata", refresh_metadata
    )
    monkeypatch.setattr(
        KnowledgeBaseQaService, "_decorate_directory_paths", AsyncMock()
    )
    db = AsyncMock()

    result = await KnowledgeBaseQaService.update(
        db,
        "T_TEST",
        7,
        7,
        KnowledgeBaseQaUpdate(directory_id=2),
    )

    assert result is item
    update.assert_awaited_once_with(db, item, {"directory_id": 2})
    assert item.process_revision == 4
    schedule.assert_not_called()
    refresh_metadata.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_processing_marks_current_revision_failed(monkeypatch):
    snapshot = qa_service._QaProcessSnapshot(
        id=7,
        revision=3,
        tenant_id="tenant",
        knowledge_base_id=2,
        question="Question",
        answer_markdown="Answer",
        enabled=True,
        access_keywords=[],
    )
    monkeypatch.setattr(
        KnowledgeBaseQaService,
        "_get_processing_snapshot",
        AsyncMock(return_value=snapshot),
    )
    mark_failed = AsyncMock()
    monkeypatch.setattr(
        KnowledgeBaseQaService, "_mark_failed_if_current", mark_failed
    )
    started = asyncio.Event()

    async def blocking_embed(_text: str):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(KnowledgeBaseQaService, "_embed", blocking_embed)

    task = asyncio.create_task(KnowledgeBaseQaService._process_background(7, 3))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    mark_failed.assert_awaited_once_with(7, 3, qa_service._INTERRUPTED_ERROR)


@pytest.mark.asyncio
async def test_embedding_slot_limits_concurrency_and_rechecks_revision(monkeypatch):
    snapshot = qa_service._QaProcessSnapshot(
        id=1,
        revision=1,
        tenant_id="tenant",
        knowledge_base_id=2,
        question="Question",
        answer_markdown="Answer",
        enabled=True,
        access_keywords=[],
    )
    get_snapshot = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(
        KnowledgeBaseQaService, "_get_processing_snapshot", get_snapshot
    )
    monkeypatch.setattr(qa_service.settings, "KB_QA_EMBEDDING_CONCURRENCY", 2)
    monkeypatch.setattr(qa_service, "_embedding_semaphore", None)
    monkeypatch.setattr(qa_service, "_embedding_semaphore_limit", None)
    active = 0
    max_active = 0

    async def worker(qa_id: int) -> None:
        nonlocal active, max_active
        async with KnowledgeBaseQaService._embedding_slot(qa_id, 1) as current:
            assert current is snapshot
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(worker(index) for index in range(5)))

    assert max_active == 2
    assert get_snapshot.await_count == 5


@pytest.mark.asyncio
async def test_recovery_marks_stale_rows_and_commits(monkeypatch):
    db = AsyncMock()

    @asynccontextmanager
    async def fake_session_scope():
        yield db

    from app.db import session as db_session

    monkeypatch.setattr(db_session, "session_scope", fake_session_scope)
    fail_stale = AsyncMock(return_value=[4])
    monkeypatch.setattr(
        KnowledgeBaseQaRepository, "fail_stale_processing", fail_stale
    )
    monkeypatch.setattr(qa_service.settings, "KB_QA_PROCESS_STALE_SECONDS", 600)

    await KnowledgeBaseQaService._recover_stale_processing()

    fail_stale.assert_awaited_once_with(
        db, timedelta(seconds=600), qa_service._STALE_ERROR
    )
    db.commit.assert_awaited_once()
