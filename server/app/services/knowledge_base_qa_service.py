"""Knowledge-base QA management and processing service."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.knowledge_paths import QA_SYSTEM_PATH_PREFIX
from app.libs.doc_parser.parser import parse_document
from app.repositories.knowledge_base_qa_repository import KnowledgeBaseQaRepository
from app.repositories.knowledge_base_qa_directory_repository import (
    KnowledgeBaseQaDirectoryRepository,
)
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.knowledge_base_qa import KnowledgeBaseQaCreate, KnowledgeBaseQaUpdate
from app.services.knowledge_base_qa_directory_service import (
    KnowledgeBaseQaDirectoryService,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.models.knowledge_base_qa import KnowledgeBaseQa

_EMBED_MAX_CHARS = 8000
_PROCESS_ERROR_MAX_CHARS = 2000
_INTERRUPTED_ERROR = "QA processing was interrupted; please retry"
_STALE_ERROR = "QA processing timed out or its worker stopped; please retry"
_background_qa_tasks: set[asyncio.Task[None]] = set()
_qa_recovery_task: asyncio.Task[None] | None = None
_embedding_semaphore: asyncio.Semaphore | None = None
_embedding_semaphore_limit: int | None = None


@dataclass(frozen=True)
class _QaProcessSnapshot:
    id: int
    revision: int
    tenant_id: str
    knowledge_base_id: int
    question: str
    answer_markdown: str
    enabled: bool
    access_keywords: list[str]


def _get_embedding_semaphore() -> asyncio.Semaphore:
    global _embedding_semaphore, _embedding_semaphore_limit

    limit = settings.KB_QA_EMBEDDING_CONCURRENCY
    if _embedding_semaphore is None or _embedding_semaphore_limit != limit:
        _embedding_semaphore = asyncio.Semaphore(limit)
        _embedding_semaphore_limit = limit
    return _embedding_semaphore


def _escape_parser_markers(value: str) -> str:
    lines: list[str] = []
    for line in value.splitlines():
        if re.fullmatch(r"[ \t]*\+\+\+[ \t]*", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines.append(f"{indent}\\+++")
            continue
        stripped = line.strip().lower()
        if stripped == "<slice-meta>":
            indent = line[: len(line) - len(line.lstrip())]
            lines.append(f"{indent}&lt;slice-meta&gt;")
            continue
        if stripped == "</slice-meta>":
            indent = line[: len(line) - len(line.lstrip())]
            lines.append(f"{indent}&lt;/slice-meta&gt;")
            continue
        lines.append(line)
    return "\n".join(lines)


def build_qa_markdown(
    *,
    question: str,
    answer_markdown: str,
    enabled: bool,
    access_keywords: list[str],
) -> str:
    keyword_lines = "\n".join(
        f"  - {json.dumps(keyword, ensure_ascii=False)}" for keyword in access_keywords
    )
    if not keyword_lines:
        keyword_lines = "  []"
    safe_question = _escape_parser_markers(question)
    safe_answer = _escape_parser_markers(answer_markdown)
    return (
        "---\n"
        f"title: {json.dumps(question, ensure_ascii=False)}\n"
        "content_type: qa\n"
        f"enabled: {'true' if enabled else 'false'}\n"
        "access_keywords:\n"
        f"{keyword_lines}\n"
        "---\n\n"
        "**Question**\n\n"
        f"{safe_question}\n\n"
        "**Answer**\n\n"
        f"{safe_answer}\n"
    )


class KnowledgeBaseQaService:
    @staticmethod
    async def _ensure_kb(
        db: AsyncSession, tenant_id: str, knowledge_base_id: int
    ):
        kb = await KnowledgeBaseRepository.get_by_id(db, knowledge_base_id)
        if not kb or kb.status == "deleted" or kb.tenant_id != tenant_id:
            raise NotFoundError("Knowledge base not found")
        return kb

    @staticmethod
    async def _ensure_directory(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        directory_id: int,
    ) -> None:
        directory = await KnowledgeBaseQaDirectoryRepository.get_by_id(
            db, tenant_id, knowledge_base_id, directory_id
        )
        if directory is None:
            raise ValidationError("QA directory is invalid")

    @staticmethod
    async def _decorate_directory_paths(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        items: list[KnowledgeBaseQa],
    ) -> None:
        directories = await KnowledgeBaseQaDirectoryRepository.list_all(
            db, tenant_id, knowledge_base_id
        )
        path_map = KnowledgeBaseQaDirectoryService.path_map(directories)
        for item in items:
            item.directory_path = path_map.get(item.directory_id, [])

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        *,
        search: str | None,
        enabled: bool | None,
        process_status: str | None,
        directory_id: int | None,
        page: int,
        per_page: int,
    ) -> dict:
        await KnowledgeBaseQaService._ensure_kb(db, tenant_id, knowledge_base_id)
        directory_ids: list[int] | None = None
        if directory_id is not None:
            await KnowledgeBaseQaService._ensure_directory(
                db, tenant_id, knowledge_base_id, directory_id
            )
            directories = await KnowledgeBaseQaDirectoryRepository.list_all(
                db, tenant_id, knowledge_base_id
            )
            directory_ids = KnowledgeBaseQaDirectoryService.subtree_ids(
                directory_id, directories
            )
        items, total = await KnowledgeBaseQaRepository.list_paginated(
            db,
            tenant_id,
            knowledge_base_id,
            search=search,
            enabled=enabled,
            process_status=process_status,
            directory_ids=directory_ids,
            page=page,
            per_page=per_page,
        )
        await KnowledgeBaseQaService._decorate_directory_paths(
            db, tenant_id, knowledge_base_id, items
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    @staticmethod
    async def get_by_id(
        db: AsyncSession, tenant_id: str, knowledge_base_id: int, qa_id: int
    ) -> KnowledgeBaseQa:
        await KnowledgeBaseQaService._ensure_kb(db, tenant_id, knowledge_base_id)
        item = await KnowledgeBaseQaRepository.get_by_id(
            db, tenant_id, knowledge_base_id, qa_id
        )
        if not item:
            raise NotFoundError("QA not found")
        await KnowledgeBaseQaService._decorate_directory_paths(
            db, tenant_id, knowledge_base_id, [item]
        )
        return item

    @staticmethod
    async def create(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        data: KnowledgeBaseQaCreate,
    ) -> KnowledgeBaseQa:
        await KnowledgeBaseQaService._ensure_kb(db, tenant_id, knowledge_base_id)
        await KnowledgeBaseQaService._ensure_directory(
            db, tenant_id, knowledge_base_id, data.directory_id
        )
        if await KnowledgeBaseQaRepository.question_exists(
            db, knowledge_base_id, data.question
        ):
            raise ConflictError("This question already exists in the knowledge base")
        try:
            item = await KnowledgeBaseQaRepository.create(
                db,
                {
                    **data.model_dump(),
                    "tenant_id": tenant_id,
                    "knowledge_base_id": knowledge_base_id,
                    "process_status": "processing",
                    "process_revision": 1,
                },
            )
            await db.commit()
            await db.refresh(item)
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError(
                "This question already exists in the knowledge base"
            ) from exc
        KnowledgeBaseQaService._schedule_processing(item.id, item.process_revision)
        await KnowledgeBaseQaService._decorate_directory_paths(
            db, tenant_id, knowledge_base_id, [item]
        )
        return item

    @staticmethod
    async def update(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        qa_id: int,
        data: KnowledgeBaseQaUpdate,
    ) -> KnowledgeBaseQa:
        item = await KnowledgeBaseQaService.get_by_id(
            db, tenant_id, knowledge_base_id, qa_id
        )
        if item.process_status == "processing":
            raise ConflictError("QA cannot be edited while processing")
        update_data = data.model_dump(exclude_unset=True)
        if "directory_id" in update_data:
            await KnowledgeBaseQaService._ensure_directory(
                db, tenant_id, knowledge_base_id, update_data["directory_id"]
            )
        question = update_data.get("question")
        if question is not None and await KnowledgeBaseQaRepository.question_exists(
            db, knowledge_base_id, question, exclude_id=qa_id
        ):
            raise ConflictError("This question already exists in the knowledge base")

        content_fields = {"question", "answer_markdown", "access_keywords"}
        content_changed = any(
            key in update_data and update_data[key] != getattr(item, key)
            for key in content_fields
        )
        enabled_changed = (
            "enabled" in update_data and update_data["enabled"] != item.enabled
        )
        if content_changed:
            update_data.update(
                {
                    "process_status": "processing",
                    "process_error": None,
                    "process_revision": item.process_revision + 1,
                }
            )
        try:
            await KnowledgeBaseQaRepository.update(db, item, update_data)
            await db.commit()
            await db.refresh(item)
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError(
                "This question already exists in the knowledge base"
            ) from exc

        if content_changed:
            KnowledgeBaseQaService._schedule_processing(item.id, item.process_revision)
        elif enabled_changed:
            await KnowledgeBaseQaService._refresh_enabled_metadata(item.id)
            await db.refresh(item)
        await KnowledgeBaseQaService._decorate_directory_paths(
            db, tenant_id, knowledge_base_id, [item]
        )
        return item

    @staticmethod
    async def toggle(
        db: AsyncSession, tenant_id: str, knowledge_base_id: int, qa_id: int
    ) -> KnowledgeBaseQa:
        item = await KnowledgeBaseQaService.get_by_id(
            db, tenant_id, knowledge_base_id, qa_id
        )
        if item.process_status == "processing":
            raise ConflictError("QA cannot be toggled while processing")
        item.enabled = not item.enabled
        await db.commit()
        await db.refresh(item)
        await KnowledgeBaseQaService._refresh_enabled_metadata(item.id)
        await db.refresh(item)
        await KnowledgeBaseQaService._decorate_directory_paths(
            db, tenant_id, knowledge_base_id, [item]
        )
        return item

    @staticmethod
    async def retry(
        db: AsyncSession, tenant_id: str, knowledge_base_id: int, qa_id: int
    ) -> KnowledgeBaseQa:
        item = await KnowledgeBaseQaService.get_by_id(
            db, tenant_id, knowledge_base_id, qa_id
        )
        if item.process_status != "failed":
            raise ConflictError("Only failed QA can be retried")
        item.process_status = "processing"
        item.process_error = None
        item.process_revision += 1
        await db.commit()
        await db.refresh(item)
        KnowledgeBaseQaService._schedule_processing(item.id, item.process_revision)
        await KnowledgeBaseQaService._decorate_directory_paths(
            db, tenant_id, knowledge_base_id, [item]
        )
        return item

    @staticmethod
    async def delete(
        db: AsyncSession, tenant_id: str, knowledge_base_id: int, qa_id: int
    ) -> None:
        item = await KnowledgeBaseQaService.get_by_id(
            db, tenant_id, knowledge_base_id, qa_id
        )
        await KnowledgeBaseQaRepository.delete_with_content(db, item)
        await db.commit()

    @staticmethod
    def _schedule_processing(qa_id: int, revision: int) -> None:
        task = asyncio.create_task(
            KnowledgeBaseQaService._process_background(qa_id, revision)
        )
        _background_qa_tasks.add(task)

        def _done(done_task: asyncio.Task[None]) -> None:
            _background_qa_tasks.discard(done_task)
            if not done_task.cancelled() and done_task.exception():
                logger.error(
                    "Unhandled QA processing error qa_id=%s: %s",
                    qa_id,
                    done_task.exception(),
                )

        task.add_done_callback(_done)

    @staticmethod
    async def start_processing_recovery() -> None:
        """Start the periodic orphaned-processing recovery loop."""
        global _qa_recovery_task

        if _qa_recovery_task is not None and not _qa_recovery_task.done():
            return
        await KnowledgeBaseQaService._recover_stale_processing()
        _qa_recovery_task = asyncio.create_task(
            KnowledgeBaseQaService._processing_recovery_loop()
        )

    @staticmethod
    async def shutdown_processing() -> None:
        """Stop recovery and make cancelled in-flight revisions retryable."""
        global _qa_recovery_task

        if _qa_recovery_task is not None:
            _qa_recovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await _qa_recovery_task
            _qa_recovery_task = None

        tasks = list(_background_qa_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _processing_recovery_loop() -> None:
        while True:
            await asyncio.sleep(settings.KB_QA_RECOVERY_INTERVAL_SECONDS)
            try:
                await KnowledgeBaseQaService._recover_stale_processing()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - recovery must survive transient DB errors
                logger.exception("Failed to recover stale QA processing rows")

    @staticmethod
    async def _recover_stale_processing() -> None:
        from app.db.session import session_scope

        async with session_scope() as db:
            ids = await KnowledgeBaseQaRepository.fail_stale_processing(
                db,
                timedelta(seconds=settings.KB_QA_PROCESS_STALE_SECONDS),
                _STALE_ERROR,
            )
            await db.commit()
        if ids:
            logger.warning(
                "Marked stale QA processing rows as failed qa_ids=%s",
                ids,
            )

    @staticmethod
    async def _mark_failed_if_current(
        qa_id: int,
        revision: int,
        error: str,
    ) -> None:
        from app.db.session import session_scope

        async with session_scope() as db:
            updated = await KnowledgeBaseQaRepository.mark_processing_failed(
                db,
                qa_id,
                revision,
                error[:_PROCESS_ERROR_MAX_CHARS],
            )
            await db.commit()
        if not updated:
            logger.info(
                "Skipped stale QA failure write qa_id=%s revision=%s",
                qa_id,
                revision,
            )

    @staticmethod
    async def _get_processing_snapshot(
        qa_id: int, revision: int
    ) -> _QaProcessSnapshot | None:
        from app.db.session import session_scope

        async with session_scope() as db:
            qa = await KnowledgeBaseQaRepository.get_unscoped(db, qa_id)
            if (
                not qa
                or qa.process_revision != revision
                or qa.process_status != "processing"
            ):
                return None
            return _QaProcessSnapshot(
                id=qa.id,
                revision=qa.process_revision,
                tenant_id=qa.tenant_id,
                knowledge_base_id=qa.knowledge_base_id,
                question=qa.question,
                answer_markdown=qa.answer_markdown,
                enabled=qa.enabled,
                access_keywords=list(qa.access_keywords or []),
            )

    @staticmethod
    @asynccontextmanager
    async def _embedding_slot(
        qa_id: int, revision: int
    ) -> AsyncIterator[_QaProcessSnapshot | None]:
        async with _get_embedding_semaphore():
            # A queued task may have been deleted, retried, or recovered while
            # waiting. Re-read after acquiring the scarce provider slot so an
            # obsolete task never incurs a paid embedding call.
            yield await KnowledgeBaseQaService._get_processing_snapshot(
                qa_id, revision
            )

    @staticmethod
    async def _process_background(qa_id: int, revision: int) -> None:
        from app.db.session import session_scope

        try:
            snapshot = await KnowledgeBaseQaService._get_processing_snapshot(
                qa_id, revision
            )
            if snapshot is None:
                return

            markdown = build_qa_markdown(
                question=snapshot.question,
                answer_markdown=snapshot.answer_markdown,
                enabled=snapshot.enabled,
                access_keywords=snapshot.access_keywords,
            )
            file_path = f"{QA_SYSTEM_PATH_PREFIX}{snapshot.id}.md"
            parsed = parse_document(file_path, markdown)
            if len(parsed.slices) != 1:
                raise RuntimeError("QA Markdown must produce exactly one slice")
            parsed_slice = parsed.slices[0]
            search_text = parsed_slice.content_for_search or parsed_slice.content
            async with KnowledgeBaseQaService._embedding_slot(
                qa_id, revision
            ) as current_snapshot:
                if current_snapshot is None:
                    return
                embedding = await KnowledgeBaseQaService._embed(search_text)

            async with session_scope() as db:
                qa = await KnowledgeBaseQaRepository.get_unscoped(db, qa_id)
                if (
                    not qa
                    or qa.process_revision != revision
                    or qa.process_status != "processing"
                ):
                    return

                await KnowledgeBaseQaRepository.save_processed_content(
                    db,
                    qa,
                    markdown=markdown,
                    file_path=file_path,
                    parsed=parsed,
                    search_text=search_text,
                    embedding=embedding,
                )
                await db.commit()
        except asyncio.CancelledError:
            await asyncio.shield(
                KnowledgeBaseQaService._mark_failed_if_current(
                    qa_id, revision, _INTERRUPTED_ERROR
                )
            )
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("QA processing failed qa_id=%s revision=%s", qa_id, revision)
            await KnowledgeBaseQaService._mark_failed_if_current(
                qa_id, revision, str(exc)
            )

    @staticmethod
    async def _embed(text_value: str) -> list[float] | None:
        from app.libs.knowledge_provider import has_embedding_credentials

        if not has_embedding_credentials():
            return None
        from app.libs.embedding.factory import create_embedding_provider

        provider = create_embedding_provider()
        vectors = await provider.embed_batch([text_value[:_EMBED_MAX_CHARS]])
        if len(vectors) != 1:
            raise RuntimeError("Embedding provider returned an invalid result")
        return vectors[0]

    @staticmethod
    async def _refresh_enabled_metadata(qa_id: int) -> None:
        from app.db.session import session_scope

        async with session_scope() as db:
            qa = await KnowledgeBaseQaRepository.get_unscoped(db, qa_id)
            if not qa or qa.document_id is None:
                return
            markdown = build_qa_markdown(
                question=qa.question,
                answer_markdown=qa.answer_markdown,
                enabled=qa.enabled,
                access_keywords=list(qa.access_keywords or []),
            )
            await KnowledgeBaseQaRepository.refresh_enabled_metadata(
                db, qa, markdown
            )
            await db.commit()
