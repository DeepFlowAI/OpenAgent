"""
Unit tests for document reference query service.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.slice_repository import SliceRepository
from app.schemas.document import DocumentQueryRequest
from app.services.document_service import DocumentService


def _doc(**overrides):
    data = {
        "id": 7,
        "knowledge_base_id": 3,
        "tenant_id": "T_DOC_QUERY",
        "title": "Guide",
        "file_path": "docs/guide.md",
        "doc_meta": {"category": "guide"},
        "markdown_content": "# Guide\nfirst line\nsecond line",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _kb(**overrides):
    data = {
        "id": 3,
        "tenant_id": "T_DOC_QUERY",
        "status": "active",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _slice(**overrides):
    data = {
        "id": 11,
        "content": "first line",
        "toc_path": ["Guide"],
        "slice_order": 2,
        "slice_meta": {"section": "intro"},
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class TestDocumentQueryService:

    @pytest.mark.asyncio
    async def test_query_reference_document_only_returns_document(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            DocumentRepository,
            "get_by_id_for_tenant",
            AsyncMock(return_value=_doc()),
        )
        monkeypatch.setattr(
            KnowledgeBaseRepository,
            "get_by_id",
            AsyncMock(return_value=_kb()),
        )

        result = await DocumentService.query_reference(
            AsyncMock(),
            "T_DOC_QUERY",
            DocumentQueryRequest(doc_id=7),
        )

        assert result.resolved is True
        assert result.reason is None
        assert result.document is not None
        assert result.document.id == 7
        assert result.document.markdown_url == "/api/v1/knowledge-bases/3/documents/7/markdown"
        assert result.document.document_url == "/knowledge-space/3/documents/7"
        assert result.slice is None
        assert result.line_text is None
        assert result.line_count is None

    @pytest.mark.asyncio
    async def test_query_reference_slice_and_line_returns_details(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            DocumentRepository,
            "get_by_id_for_tenant",
            AsyncMock(return_value=_doc()),
        )
        monkeypatch.setattr(
            KnowledgeBaseRepository,
            "get_by_id",
            AsyncMock(return_value=_kb()),
        )
        monkeypatch.setattr(
            SliceRepository,
            "get_by_id_for_document",
            AsyncMock(return_value=_slice()),
        )

        result = await DocumentService.query_reference(
            AsyncMock(),
            "T_DOC_QUERY",
            DocumentQueryRequest(doc_id=7, slice_id=11, line=2),
        )

        assert result.resolved is True
        assert result.reason is None
        assert result.slice is not None
        assert result.slice.id == 11
        assert result.slice.slice_meta == {"section": "intro"}
        assert result.line_text == "first line"
        assert result.line_count == 3

    @pytest.mark.asyncio
    async def test_query_reference_missing_document_returns_unresolved(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            DocumentRepository,
            "get_by_id_for_tenant",
            AsyncMock(return_value=None),
        )

        result = await DocumentService.query_reference(
            AsyncMock(),
            "T_DOC_QUERY",
            DocumentQueryRequest(doc_id=999),
        )

        assert result.resolved is False
        assert result.reason == "document_not_found"
        assert result.document is None

    @pytest.mark.asyncio
    async def test_query_reference_deleted_kb_returns_document_not_found(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            DocumentRepository,
            "get_by_id_for_tenant",
            AsyncMock(return_value=_doc()),
        )
        monkeypatch.setattr(
            KnowledgeBaseRepository,
            "get_by_id",
            AsyncMock(return_value=_kb(status="deleted")),
        )

        result = await DocumentService.query_reference(
            AsyncMock(),
            "T_DOC_QUERY",
            DocumentQueryRequest(doc_id=7),
        )

        assert result.resolved is False
        assert result.reason == "document_not_found"
        assert result.document is None

    @pytest.mark.asyncio
    async def test_query_reference_missing_slice_returns_document_with_reason(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            DocumentRepository,
            "get_by_id_for_tenant",
            AsyncMock(return_value=_doc()),
        )
        monkeypatch.setattr(
            KnowledgeBaseRepository,
            "get_by_id",
            AsyncMock(return_value=_kb()),
        )
        monkeypatch.setattr(
            SliceRepository,
            "get_by_id_for_document",
            AsyncMock(return_value=None),
        )

        result = await DocumentService.query_reference(
            AsyncMock(),
            "T_DOC_QUERY",
            DocumentQueryRequest(doc_id=7, slice_id=999),
        )

        assert result.resolved is False
        assert result.reason == "slice_not_found"
        assert result.document is not None
        assert result.slice is None

    @pytest.mark.asyncio
    async def test_query_reference_missing_line_returns_document_with_line_count(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            DocumentRepository,
            "get_by_id_for_tenant",
            AsyncMock(return_value=_doc()),
        )
        monkeypatch.setattr(
            KnowledgeBaseRepository,
            "get_by_id",
            AsyncMock(return_value=_kb()),
        )

        result = await DocumentService.query_reference(
            AsyncMock(),
            "T_DOC_QUERY",
            DocumentQueryRequest(doc_id=7, line=9),
        )

        assert result.resolved is False
        assert result.reason == "line_not_found"
        assert result.line_text is None
        assert result.line_count == 3
