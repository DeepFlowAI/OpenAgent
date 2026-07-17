"""Unit tests for knowledge-base QA directory rules."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as PydanticValidationError
from starlette.requests import Request

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.db.deps import AuthContext, require_admin_session, require_user_session
from app.repositories.knowledge_base_qa_directory_repository import (
    KnowledgeBaseQaDirectoryRepository,
)
from app.schemas.knowledge_base_qa_directory import (
    KnowledgeBaseQaDirectoryCreate,
    KnowledgeBaseQaDirectoryUpdate,
)
from app.services.knowledge_base_qa_directory_service import (
    KnowledgeBaseQaDirectoryService,
)


def directory(
    item_id: int,
    name: str,
    parent_id: int | None,
    sort_order: int = 0,
) -> SimpleNamespace:
    now = datetime.now()
    return SimpleNamespace(
        id=item_id,
        tenant_id="T_TEST",
        knowledge_base_id=7,
        parent_id=parent_id,
        name=name,
        sort_order=sort_order,
        created_at=now,
        updated_at=now,
    )


class TestKnowledgeBaseQaDirectorySchema:
    def test_name_is_trimmed(self):
        data = KnowledgeBaseQaDirectoryCreate(name="  售后  ")

        assert data.name == "售后"

    @pytest.mark.parametrize("name", ["", "   ", "x" * 51])
    def test_invalid_name_is_rejected(self, name: str):
        with pytest.raises(PydanticValidationError):
            KnowledgeBaseQaDirectoryCreate(name=name)


class TestKnowledgeBaseQaDirectoryTree:
    def test_paths_depths_and_subtree_counts_are_computed(self):
        items = [
            directory(1, "产品", None),
            directory(2, "售后", 1),
            directory(3, "退款", 2),
        ]

        result = KnowledgeBaseQaDirectoryService._serialize(
            items, {1: 1, 2: 2, 3: 3}
        )

        by_id = {item["id"]: item for item in result}
        assert by_id[1]["qa_count"] == 6
        assert by_id[2]["qa_count"] == 5
        assert by_id[3]["path"] == ["产品", "售后", "退款"]
        assert by_id[3]["depth"] == 3

    @pytest.mark.asyncio
    async def test_create_under_third_level_is_rejected(self, monkeypatch):
        items = [
            directory(1, "产品", None),
            directory(2, "售后", 1),
            directory(3, "退款", 2),
        ]
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryService, "_ensure_kb", AsyncMock()
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "list_all",
            AsyncMock(return_value=items),
        )

        with pytest.raises(ValidationError, match="up to 3 levels"):
            await KnowledgeBaseQaDirectoryService.create(
                AsyncMock(),
                "T_TEST",
                7,
                KnowledgeBaseQaDirectoryCreate(name="超过三级", parent_id=3),
            )

    @pytest.mark.asyncio
    async def test_move_into_descendant_is_rejected(self, monkeypatch):
        root = directory(1, "产品", None)
        child = directory(2, "售后", 1)
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryService, "_ensure_kb", AsyncMock()
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "get_by_id",
            AsyncMock(return_value=root),
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "list_all",
            AsyncMock(return_value=[root, child]),
        )

        with pytest.raises(ValidationError, match="descendant"):
            await KnowledgeBaseQaDirectoryService.update(
                AsyncMock(),
                "T_TEST",
                7,
                1,
                KnowledgeBaseQaDirectoryUpdate(parent_id=2),
            )

    @pytest.mark.asyncio
    async def test_move_and_rename_are_flushed_together_under_target_parent(
        self, monkeypatch
    ):
        old_parent = directory(1, "旧分组", None)
        new_parent = directory(2, "新分组", None, 1)
        item = directory(3, "旧名称", 1)
        events: list[str] = []
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryService, "_ensure_kb", AsyncMock()
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryService,
            "_response_for",
            AsyncMock(return_value={"id": 3}),
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "get_by_id",
            AsyncMock(return_value=item),
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "list_all",
            AsyncMock(return_value=[old_parent, new_parent, item]),
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "name_exists",
            AsyncMock(return_value=False),
        )

        async def list_siblings(_db, _tenant, _kb, parent_id, **_kwargs):
            events.append(f"siblings:{parent_id}")
            return []

        async def apply_order(_db, _items, parent_id):
            events.append(f"order:{parent_id}")

        async def update_fields(_db, current, data):
            events.append("name")
            current.name = data["name"]

        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository, "list_siblings", list_siblings
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository, "apply_order", apply_order
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository, "update_fields", update_fields
        )
        db = AsyncMock()

        await KnowledgeBaseQaDirectoryService.update(
            db,
            "T_TEST",
            7,
            3,
            KnowledgeBaseQaDirectoryUpdate(
                name="新名称", parent_id=2, sort_order=0
            ),
        )

        assert events == [
            "siblings:1",
            "order:1",
            "siblings:2",
            "name",
            "order:2",
        ]

    @pytest.mark.asyncio
    async def test_duplicate_name_is_rejected(self, monkeypatch):
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryService, "_ensure_kb", AsyncMock()
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "list_all",
            AsyncMock(return_value=[]),
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "name_exists",
            AsyncMock(return_value=True),
        )

        with pytest.raises(ConflictError, match="already exists"):
            await KnowledgeBaseQaDirectoryService.create(
                AsyncMock(),
                "T_TEST",
                7,
                KnowledgeBaseQaDirectoryCreate(name="产品"),
            )

    @pytest.mark.asyncio
    async def test_non_empty_directory_cannot_be_deleted(self, monkeypatch):
        item = directory(1, "产品", None)
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryService, "_ensure_kb", AsyncMock()
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "get_by_id",
            AsyncMock(return_value=item),
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "has_children",
            AsyncMock(return_value=True),
        )

        with pytest.raises(ConflictError, match="contains content"):
            await KnowledgeBaseQaDirectoryService.delete(
                AsyncMock(), "T_TEST", 7, 1
            )

    @pytest.mark.asyncio
    async def test_directory_with_direct_qas_cannot_be_deleted(self, monkeypatch):
        item = directory(1, "产品", None)
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryService, "_ensure_kb", AsyncMock()
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "get_by_id",
            AsyncMock(return_value=item),
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "has_children",
            AsyncMock(return_value=False),
        )
        monkeypatch.setattr(
            KnowledgeBaseQaDirectoryRepository,
            "has_direct_qas",
            AsyncMock(return_value=True),
        )

        with pytest.raises(ConflictError, match="contains content"):
            await KnowledgeBaseQaDirectoryService.delete(
                AsyncMock(), "T_TEST", 7, 1
            )


class TestKnowledgeBaseQaDirectoryAuth:
    @pytest.mark.asyncio
    async def test_user_session_accepts_member_jwt_for_read(self):
        request = Request(
            {"type": "http", "headers": [(b"authorization", b"Bearer jwt-token")]}
        )
        auth = AuthContext(tenant_id="T_TEST", scopes=None, role="member")

        assert await require_user_session(request, auth) is auth

    @pytest.mark.asyncio
    async def test_user_session_rejects_api_key(self):
        request = Request(
            {"type": "http", "headers": [(b"authorization", b"Bearer sk-test")]}
        )
        auth = AuthContext(tenant_id="T_TEST", scopes=["chat"])

        with pytest.raises(ForbiddenError):
            await require_user_session(request, auth)

    @pytest.mark.asyncio
    async def test_admin_session_rejects_member(self):
        with pytest.raises(ForbiddenError, match="management permission"):
            await require_admin_session(
                AuthContext(tenant_id="T_TEST", scopes=None, role="member")
            )
