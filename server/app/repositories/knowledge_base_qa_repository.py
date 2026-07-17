"""Knowledge-base QA repository."""

from datetime import timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.libs.doc_parser.parser import ParsedDocument
from app.models.knowledge_base_qa import KnowledgeBaseQa
from app.models.document import Document
from app.models.slice import Slice


class KnowledgeBaseQaRepository:
    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        qa_id: int,
    ) -> KnowledgeBaseQa | None:
        result = await db.execute(
            select(KnowledgeBaseQa).where(
                KnowledgeBaseQa.id == qa_id,
                KnowledgeBaseQa.tenant_id == tenant_id,
                KnowledgeBaseQa.knowledge_base_id == knowledge_base_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_unscoped(db: AsyncSession, qa_id: int) -> KnowledgeBaseQa | None:
        return await db.get(KnowledgeBaseQa, qa_id)

    @staticmethod
    async def list_paginated(
        db: AsyncSession,
        tenant_id: str,
        knowledge_base_id: int,
        *,
        search: str | None,
        enabled: bool | None,
        process_status: str | None,
        directory_ids: list[int] | None,
        page: int,
        per_page: int,
    ) -> tuple[list[KnowledgeBaseQa], int]:
        conditions = [
            KnowledgeBaseQa.tenant_id == tenant_id,
            KnowledgeBaseQa.knowledge_base_id == knowledge_base_id,
        ]
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                or_(
                    KnowledgeBaseQa.question.ilike(pattern),
                    KnowledgeBaseQa.answer_markdown.ilike(pattern),
                )
            )
        if enabled is not None:
            conditions.append(KnowledgeBaseQa.enabled.is_(enabled))
        if process_status:
            conditions.append(KnowledgeBaseQa.process_status == process_status)
        if directory_ids is not None:
            conditions.append(KnowledgeBaseQa.directory_id.in_(directory_ids))

        total = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(KnowledgeBaseQa)
                    .where(*conditions)
                )
            ).scalar_one()
        )
        result = await db.execute(
            select(KnowledgeBaseQa)
            .where(*conditions)
            .order_by(KnowledgeBaseQa.updated_at.desc(), KnowledgeBaseQa.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def question_exists(
        db: AsyncSession,
        knowledge_base_id: int,
        question: str,
        *,
        exclude_id: int | None = None,
    ) -> bool:
        stmt = select(KnowledgeBaseQa.id).where(
            KnowledgeBaseQa.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseQa.question == question,
        )
        if exclude_id is not None:
            stmt = stmt.where(KnowledgeBaseQa.id != exclude_id)
        return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> KnowledgeBaseQa:
        item = KnowledgeBaseQa(**data)
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def update(
        db: AsyncSession, item: KnowledgeBaseQa, data: dict
    ) -> KnowledgeBaseQa:
        for key, value in data.items():
            setattr(item, key, value)
        await db.flush()
        return item

    @staticmethod
    async def mark_processing_failed(
        db: AsyncSession,
        qa_id: int,
        revision: int,
        error: str,
    ) -> bool:
        """Fail only the still-current processing revision."""
        result = await db.execute(
            update(KnowledgeBaseQa)
            .where(
                KnowledgeBaseQa.id == qa_id,
                KnowledgeBaseQa.process_revision == revision,
                KnowledgeBaseQa.process_status == "processing",
            )
            .values(process_status="failed", process_error=error)
            .returning(KnowledgeBaseQa.id)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def fail_stale_processing(
        db: AsyncSession,
        stale_after: timedelta,
        error: str,
    ) -> list[int]:
        """Atomically make orphaned processing rows retryable."""
        result = await db.execute(
            update(KnowledgeBaseQa)
            .where(
                KnowledgeBaseQa.process_status == "processing",
                KnowledgeBaseQa.updated_at < func.now() - stale_after,
            )
            .values(process_status="failed", process_error=error)
            .returning(KnowledgeBaseQa.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def delete_all_by_kb(db: AsyncSession, knowledge_base_id: int) -> None:
        doc_ids = select(KnowledgeBaseQa.document_id).where(
            KnowledgeBaseQa.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseQa.document_id.isnot(None),
        )
        await db.execute(delete(Slice).where(Slice.document_id.in_(doc_ids)))
        await db.execute(
            delete(KnowledgeBaseQa).where(
                KnowledgeBaseQa.knowledge_base_id == knowledge_base_id
            )
        )
        await db.execute(
            delete(Document).where(
                Document.knowledge_base_id == knowledge_base_id,
                Document.source_type == "qa",
            )
        )
        await db.flush()

    @staticmethod
    async def delete_with_content(
        db: AsyncSession, item: KnowledgeBaseQa
    ) -> None:
        document_id = item.document_id
        await db.delete(item)
        if document_id is not None:
            await db.execute(delete(Slice).where(Slice.document_id == document_id))
            await db.execute(
                delete(Document).where(
                    Document.id == document_id,
                    Document.source_type == "qa",
                )
            )
        await db.flush()

    @staticmethod
    async def save_processed_content(
        db: AsyncSession,
        qa: KnowledgeBaseQa,
        *,
        markdown: str,
        file_path: str,
        parsed: ParsedDocument,
        search_text: str,
        embedding: list[float] | None,
    ) -> None:
        document: Document | None = None
        if qa.document_id is not None:
            document = await db.get(Document, qa.document_id)
            if document and document.source_type != "qa":
                raise RuntimeError("QA document source mismatch")
        doc_meta = {
            **(parsed.doc_meta or {}),
            "content_type": "qa",
            "enabled": qa.enabled,
            "access_keywords": list(qa.access_keywords or []),
            "qa_id": qa.id,
        }
        if document is None:
            document = Document(
                knowledge_base_id=qa.knowledge_base_id,
                tenant_id=qa.tenant_id,
                title=qa.question,
                file_path=file_path,
                markdown_content=markdown,
                doc_meta=doc_meta,
                toc=parsed.toc or None,
                slice_count=1,
                source_type="qa",
            )
            db.add(document)
            await db.flush()
            qa.document_id = document.id
        else:
            await db.execute(delete(Slice).where(Slice.document_id == document.id))
            document.title = qa.question
            document.file_path = file_path
            document.markdown_content = markdown
            document.doc_meta = doc_meta
            document.toc = parsed.toc or None
            document.slice_count = 1

        parsed_slice = parsed.slices[0]
        db.add(
            Slice(
                document_id=document.id,
                knowledge_base_id=qa.knowledge_base_id,
                tenant_id=qa.tenant_id,
                content=parsed_slice.content,
                content_for_search=search_text,
                toc_path=parsed_slice.toc_path or None,
                toc_ancestors=parsed_slice.toc_ancestors,
                slice_meta=parsed_slice.slice_meta or None,
                doc_meta=doc_meta,
                markdown_url=f"/knowledge-space/{qa.knowledge_base_id}/qa/{qa.id}",
                slice_order=0,
                embedding=embedding,
            )
        )
        qa.process_status = "ready"
        qa.process_error = None
        await db.flush()

    @staticmethod
    async def refresh_enabled_metadata(
        db: AsyncSession, qa: KnowledgeBaseQa, markdown: str
    ) -> None:
        if qa.document_id is None:
            return
        document = await db.get(Document, qa.document_id)
        if not document or document.source_type != "qa":
            return
        doc_meta = dict(document.doc_meta or {})
        doc_meta["enabled"] = qa.enabled
        document.markdown_content = markdown
        document.doc_meta = doc_meta
        slices = list(
            (
                await db.execute(select(Slice).where(Slice.document_id == document.id))
            ).scalars()
        )
        for item in slices:
            item.doc_meta = doc_meta
        await db.flush()
