"""Knowledge-base QA directory business rules."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.knowledge_base_qa_directory import KnowledgeBaseQaDirectory
from app.repositories.knowledge_base_qa_directory_repository import (
    KnowledgeBaseQaDirectoryRepository,
)
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.knowledge_base_qa_directory import (
    KnowledgeBaseQaDirectoryCreate,
    KnowledgeBaseQaDirectoryUpdate,
)

_MAX_DEPTH = 3


class KnowledgeBaseQaDirectoryService:
    @staticmethod
    async def _ensure_kb(
        db: AsyncSession, tenant_id: str, knowledge_base_id: int
    ) -> None:
        kb = await KnowledgeBaseRepository.get_by_id(db, knowledge_base_id)
        if not kb or kb.status == "deleted" or kb.tenant_id != tenant_id:
            raise NotFoundError("Knowledge base not found")

    @staticmethod
    def _depth(
        item: KnowledgeBaseQaDirectory,
        by_id: dict[int, KnowledgeBaseQaDirectory],
    ) -> int:
        depth = 1
        parent_id = item.parent_id
        seen = {item.id}
        while parent_id is not None:
            if parent_id in seen or parent_id not in by_id:
                raise ValidationError("Invalid QA directory hierarchy")
            seen.add(parent_id)
            depth += 1
            parent_id = by_id[parent_id].parent_id
        return depth

    @staticmethod
    def _subtree_height(
        directory_id: int,
        items: list[KnowledgeBaseQaDirectory],
    ) -> int:
        children: dict[int, list[int]] = {}
        for item in items:
            if item.parent_id is not None:
                children.setdefault(item.parent_id, []).append(item.id)

        def height(item_id: int, seen: set[int]) -> int:
            if item_id in seen:
                raise ValidationError("Invalid QA directory hierarchy")
            next_seen = {*seen, item_id}
            return 1 + max(
                (height(child_id, next_seen) for child_id in children.get(item_id, [])),
                default=0,
            )

        return height(directory_id, set())

    @staticmethod
    def _serialize(
        items: list[KnowledgeBaseQaDirectory], direct_counts: dict[int, int]
    ) -> list[dict]:
        by_id = {item.id: item for item in items}
        children: dict[int, list[int]] = {}
        for item in items:
            if item.parent_id is not None:
                children.setdefault(item.parent_id, []).append(item.id)

        cache: dict[int, tuple[int, list[str], int]] = {}

        def values(item: KnowledgeBaseQaDirectory) -> tuple[int, list[str], int]:
            if item.id in cache:
                return cache[item.id]
            depth = KnowledgeBaseQaDirectoryService._depth(item, by_id)
            path = [item.name]
            parent_id = item.parent_id
            while parent_id is not None:
                parent = by_id[parent_id]
                path.append(parent.name)
                parent_id = parent.parent_id
            subtree_count = direct_counts.get(item.id, 0) + sum(
                values(by_id[child_id])[2] for child_id in children.get(item.id, [])
            )
            result = (depth, list(reversed(path)), subtree_count)
            cache[item.id] = result
            return result

        response: list[dict] = []
        for item in items:
            depth, path, qa_count = values(item)
            response.append(
                {
                    "id": item.id,
                    "tenant_id": item.tenant_id,
                    "knowledge_base_id": item.knowledge_base_id,
                    "parent_id": item.parent_id,
                    "name": item.name,
                    "sort_order": item.sort_order,
                    "depth": depth,
                    "path": path,
                    "qa_count": qa_count,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
            )
        return response

    @staticmethod
    def path_map(items: list[KnowledgeBaseQaDirectory]) -> dict[int, list[str]]:
        return {
            item["id"]: item["path"]
            for item in KnowledgeBaseQaDirectoryService._serialize(items, {})
        }

    @staticmethod
    def subtree_ids(
        directory_id: int, items: list[KnowledgeBaseQaDirectory]
    ) -> list[int]:
        by_id = {item.id: item for item in items}
        if directory_id not in by_id:
            return []
        children: dict[int, list[int]] = {}
        for item in items:
            if item.parent_id is not None:
                children.setdefault(item.parent_id, []).append(item.id)
        result: list[int] = []
        pending = [directory_id]
        while pending:
            current = pending.pop()
            result.append(current)
            pending.extend(children.get(current, []))
        return result

    @staticmethod
    async def list_directories(
        db: AsyncSession, tenant_id: str, knowledge_base_id: int
    ) -> dict:
        await KnowledgeBaseQaDirectoryService._ensure_kb(
            db, tenant_id, knowledge_base_id
        )
        items = await KnowledgeBaseQaDirectoryRepository.list_all(
            db, tenant_id, knowledge_base_id
        )
        direct_counts = (
            await KnowledgeBaseQaDirectoryRepository.count_qas_by_directory(
                db, knowledge_base_id
            )
        )
        return {
            "items": KnowledgeBaseQaDirectoryService._serialize(items, direct_counts),
            "total_qa_count": await KnowledgeBaseQaDirectoryRepository.count_qas(
                db, knowledge_base_id
            ),
        }

    @staticmethod
    async def _response_for(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        directory_id: int,
    ) -> dict:
        result = await KnowledgeBaseQaDirectoryService.list_directories(
            db, tenant_id, knowledge_base_id
        )
        return next(item for item in result["items"] if item["id"] == directory_id)

    @staticmethod
    async def create(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        data: KnowledgeBaseQaDirectoryCreate,
    ) -> dict:
        await KnowledgeBaseQaDirectoryService._ensure_kb(
            db, tenant_id, knowledge_base_id
        )
        items = await KnowledgeBaseQaDirectoryRepository.list_all(
            db, tenant_id, knowledge_base_id
        )
        by_id = {item.id: item for item in items}
        if data.parent_id is not None:
            parent = by_id.get(data.parent_id)
            if parent is None:
                raise ValidationError("Parent QA directory is invalid")
            if KnowledgeBaseQaDirectoryService._depth(parent, by_id) >= _MAX_DEPTH:
                raise ValidationError("QA directories support up to 3 levels")
        if await KnowledgeBaseQaDirectoryRepository.name_exists(
            db, knowledge_base_id, data.parent_id, data.name
        ):
            raise ConflictError(
                "A directory with this name already exists under the same parent"
            )
        siblings = await KnowledgeBaseQaDirectoryRepository.list_siblings(
            db, tenant_id, knowledge_base_id, data.parent_id
        )
        try:
            item = await KnowledgeBaseQaDirectoryRepository.create(
                db,
                {
                    "tenant_id": tenant_id,
                    "knowledge_base_id": knowledge_base_id,
                    "parent_id": data.parent_id,
                    "name": data.name,
                    "sort_order": len(siblings),
                },
            )
            await db.commit()
            await db.refresh(item)
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError(
                "A directory with this name already exists under the same parent"
            ) from exc
        return await KnowledgeBaseQaDirectoryService._response_for(
            db, tenant_id, knowledge_base_id, item.id
        )

    @staticmethod
    async def update(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        directory_id: int,
        data: KnowledgeBaseQaDirectoryUpdate,
    ) -> dict:
        await KnowledgeBaseQaDirectoryService._ensure_kb(
            db, tenant_id, knowledge_base_id
        )
        item = await KnowledgeBaseQaDirectoryRepository.get_by_id(
            db, tenant_id, knowledge_base_id, directory_id
        )
        if item is None:
            raise NotFoundError("QA directory not found")

        update_data = data.model_dump(exclude_unset=True)
        target_parent_id = (
            update_data["parent_id"]
            if "parent_id" in update_data
            else item.parent_id
        )
        target_name = update_data.get("name", item.name)
        all_items = await KnowledgeBaseQaDirectoryRepository.list_all(
            db, tenant_id, knowledge_base_id
        )
        by_id = {current.id: current for current in all_items}

        if target_parent_id == item.id:
            raise ValidationError("A QA directory cannot be moved into itself")
        if target_parent_id is not None:
            parent = by_id.get(target_parent_id)
            if parent is None:
                raise ValidationError("Parent QA directory is invalid")
            parent_id = parent.parent_id
            while parent_id is not None:
                if parent_id == item.id:
                    raise ValidationError(
                        "A QA directory cannot be moved into its descendant"
                    )
                parent_id = by_id[parent_id].parent_id
            target_depth = KnowledgeBaseQaDirectoryService._depth(parent, by_id) + 1
        else:
            target_depth = 1
        subtree_height = KnowledgeBaseQaDirectoryService._subtree_height(
            item.id, all_items
        )
        if target_depth + subtree_height - 1 > _MAX_DEPTH:
            raise ValidationError("QA directories support up to 3 levels")
        if await KnowledgeBaseQaDirectoryRepository.name_exists(
            db,
            knowledge_base_id,
            target_parent_id,
            target_name,
            exclude_id=item.id,
        ):
            raise ConflictError(
                "A directory with this name already exists under the same parent"
            )

        old_parent_id = item.parent_id
        parent_changed = target_parent_id != old_parent_id
        order_changed = "sort_order" in update_data
        try:
            if parent_changed or order_changed:
                old_siblings = await KnowledgeBaseQaDirectoryRepository.list_siblings(
                    db,
                    tenant_id,
                    knowledge_base_id,
                    old_parent_id,
                    exclude_id=item.id,
                )
                if parent_changed:
                    await KnowledgeBaseQaDirectoryRepository.apply_order(
                        db, old_siblings, old_parent_id
                    )
                    target_siblings = await KnowledgeBaseQaDirectoryRepository.list_siblings(
                        db,
                        tenant_id,
                        knowledge_base_id,
                        target_parent_id,
                        exclude_id=item.id,
                    )
                else:
                    target_siblings = old_siblings
                if "name" in update_data:
                    await KnowledgeBaseQaDirectoryRepository.update_fields(
                        db, item, {"name": target_name}
                    )
                insert_at = min(
                    update_data.get("sort_order", len(target_siblings)),
                    len(target_siblings),
                )
                target_siblings.insert(insert_at, item)
                await KnowledgeBaseQaDirectoryRepository.apply_order(
                    db, target_siblings, target_parent_id
                )
            elif "name" in update_data:
                await KnowledgeBaseQaDirectoryRepository.update_fields(
                    db, item, {"name": target_name}
                )
            await db.commit()
            await db.refresh(item)
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError(
                "A directory with this name already exists under the same parent"
            ) from exc
        return await KnowledgeBaseQaDirectoryService._response_for(
            db, tenant_id, knowledge_base_id, item.id
        )

    @staticmethod
    async def delete(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        directory_id: int,
    ) -> None:
        await KnowledgeBaseQaDirectoryService._ensure_kb(
            db, tenant_id, knowledge_base_id
        )
        item = await KnowledgeBaseQaDirectoryRepository.get_by_id(
            db, tenant_id, knowledge_base_id, directory_id
        )
        if item is None:
            raise NotFoundError("QA directory not found")
        if await KnowledgeBaseQaDirectoryRepository.has_children(db, item.id):
            raise ConflictError(
                "This directory still contains content. Move or delete it first."
            )
        if await KnowledgeBaseQaDirectoryRepository.has_direct_qas(db, item.id):
            raise ConflictError(
                "This directory still contains content. Move or delete it first."
            )
        siblings = await KnowledgeBaseQaDirectoryRepository.list_siblings(
            db,
            tenant_id,
            knowledge_base_id,
            item.parent_id,
            exclude_id=item.id,
        )
        await KnowledgeBaseQaDirectoryRepository.delete(db, item.id)
        await KnowledgeBaseQaDirectoryRepository.apply_order(
            db, siblings, item.parent_id
        )
        await db.commit()
