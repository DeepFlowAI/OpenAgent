"""
Integration tests for document reference query API.
"""
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.schemas.document import DocumentQueryDocument, DocumentQueryResponse
from app.services.document_service import DocumentService


class TestDocumentQueryAPI:

    @pytest.mark.asyncio
    async def test_query_document_route_returns_service_payload(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        async def fake_query_reference(db, tenant_id, body):
            assert tenant_id == "T_DOC_QUERY_ROUTE"
            assert body.doc_id == 7
            return DocumentQueryResponse(
                resolved=True,
                doc_id=7,
                document=DocumentQueryDocument(
                    id=7,
                    knowledge_base_id=3,
                    title="Guide",
                    file_path="docs/guide.md",
                    doc_meta={"category": "guide"},
                    markdown_url="/api/v1/knowledge-bases/3/documents/7/markdown",
                    document_url="/knowledge-space/3/documents/7",
                ),
            )

        mock_service = AsyncMock(side_effect=fake_query_reference)
        monkeypatch.setattr(DocumentService, "query_reference", mock_service)

        response = await client.post(
            "/api/v1/documents/query",
            params={"tenant_id": "T_DOC_QUERY_ROUTE"},
            json={"doc_id": 7},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["resolved"] is True
        assert data["document"]["id"] == 7
        mock_service.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_document_route_requires_auth(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents/query",
            json={"doc_id": 7},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_query_document_route_rejects_invalid_parameters(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        mock_service = AsyncMock()
        monkeypatch.setattr(DocumentService, "query_reference", mock_service)

        response = await client.post(
            "/api/v1/documents/query",
            params={"tenant_id": "T_DOC_QUERY_INVALID"},
            json={"doc_id": 0},
        )

        assert response.status_code == 422
        mock_service.assert_not_awaited()
