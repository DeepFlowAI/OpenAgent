"""
Sync service — orchestrates Git pull + document parsing + DB import.

Supports two sync modes:
- full: delete all documents & slices, re-import everything
- incremental: only process added/modified/deleted files based on content hash
"""
import hashlib
import logging
import os
import tempfile
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.libs.git_sync.provider import GitSyncService
from app.libs.doc_parser.parser import (
    parse_document,
    discover_markdown_files,
    ParsedDocument,
)
from app.libs.doc_parser.schema_loader import (
    load_schema,
    extract_schema_fields,
    extract_schema_definitions,
    get_field_type_map,
)
from app.libs.doc_parser.nav_loader import load_nav_config
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.slice_repository import SliceRepository
from app.repositories.sync_log_repository import SyncLogRepository

logger = logging.getLogger(__name__)

_DOC_TITLE_MAX = 256
_DOC_FILE_PATH_MAX = 512
_DOC_SOURCE_URL_MAX = 1024

_EMBED_MAX_CHARS_PER_TEXT = 8000
_EMBED_BATCH_SIZE = 8


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def _compute_schema_hash(repo_path: str) -> str:
    """SHA-256 of concatenated schema file contents."""
    parts: list[str] = []
    for filename in ("doc-meta.yaml", "slice-meta.yaml"):
        path = os.path.join(repo_path, "schema", filename)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f"{filename}:{f.read()}")
        else:
            parts.append(f"{filename}:")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _compute_content_hash(content: str) -> str:
    """SHA-256 of raw markdown content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _classify_files(
    discovered: dict[str, str],
    existing: dict[str, tuple[int, str | None]],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """
    Classify files into (added, modified, unchanged, deleted).

    Args:
        discovered: {file_path: content_hash} from filesystem
        existing: {file_path: (doc_id, content_hash)} from DB
    """
    disc_set = set(discovered)
    exist_set = set(existing)

    added = sorted(disc_set - exist_set)
    deleted = sorted(exist_set - disc_set)
    common = disc_set & exist_set

    modified = sorted(
        fp for fp in common
        if existing[fp][1] is None or discovered[fp] != existing[fp][1]
    )
    unchanged = sorted(
        fp for fp in common
        if existing[fp][1] is not None and discovered[fp] == existing[fp][1]
    )
    return added, modified, unchanged, deleted


# ---------------------------------------------------------------------------
# SyncService
# ---------------------------------------------------------------------------

class SyncService:

    @staticmethod
    async def sync_and_parse(
        db: AsyncSession, kb_id: int, *, force_full: bool = False,
    ) -> dict:
        """Sync pipeline: git pull → detect changes → parse & import."""
        kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not kb or kb.status == "deleted":
            raise NotFoundError("Knowledge base not found")

        sync_log = await SyncLogRepository.create(db, {
            "knowledge_base_id": kb.id,
            "tenant_id": kb.tenant_id,
            "status": "running",
        })
        await db.commit()
        sync_log_id = sync_log.id

        work_dir = None
        try:
            work_dir = tempfile.mkdtemp(prefix=f"kb_{kb.id}_")
            repo_path = GitSyncService.sync_repo(
                git_url=kb.git_url,
                branch=kb.git_branch,
                auth_token=kb.auth_token,
                work_dir=work_dir,
            )

            doc_schema_data = load_schema(repo_path, "doc-meta.yaml")
            slice_schema_data = load_schema(repo_path, "slice-meta.yaml")
            doc_field_types = get_field_type_map(doc_schema_data)
            slice_field_types = get_field_type_map(slice_schema_data)

            current_schema_hash = _compute_schema_hash(repo_path)
            current_schema_fields = extract_schema_fields(repo_path)
            current_schema_defs = extract_schema_definitions(repo_path)
            stored_schema_hash = kb.schema_hash
            schema_changed = (
                stored_schema_hash is None
                or current_schema_hash != stored_schema_hash
            )
            sync_mode = "full" if (force_full or schema_changed) else "incremental"

            md_files = discover_markdown_files(repo_path)
            total_files = len(md_files)
            logger.info(
                "Sync kb_id=%s: mode=%s schema_changed=%s discovered %d file(s)",
                kb.id, sync_mode, schema_changed, total_files,
            )

            if sync_mode == "full":
                result = await SyncService._sync_full(
                    db, kb, repo_path, md_files, current_schema_hash,
                    doc_field_types=doc_field_types,
                    slice_field_types=slice_field_types,
                )
            else:
                result = await SyncService._sync_incremental(
                    db, kb, repo_path, md_files, current_schema_hash,
                    doc_field_types=doc_field_types,
                    slice_field_types=slice_field_types,
                )

            details = result["details"]
            success_count = result["success_count"]
            error_count = result["error_count"]
            total_doc_count = result["total_doc_count"]

            nav_config = load_nav_config(repo_path)

            kb_row = await KnowledgeBaseRepository.get_by_id(db, kb_id)
            if kb_row:
                kb_row.last_synced_at = datetime.utcnow()
                kb_row.document_count = total_doc_count
                kb_row.schema_hash = current_schema_hash
                kb_row.schema_fields = {
                    **current_schema_fields,
                    **current_schema_defs,
                }
                kb_row.nav_config = nav_config

            log_row = await SyncLogRepository.get_by_id(db, sync_log_id)
            if not log_row:
                raise RuntimeError(f"sync_log id={sync_log_id} missing after sync")

            job_status = "success" if error_count == 0 else "partial_success"

            sync_details: dict = {
                "sync_mode": sync_mode,
                "schema_changed": schema_changed,
                "added_count": result.get("added_count", 0),
                "modified_count": result.get("modified_count", 0),
                "unchanged_count": result.get("unchanged_count", 0),
                "deleted_count": result.get("deleted_count", 0),
                "files": details,
            }

            await SyncLogRepository.update(db, log_row, {
                "status": job_status,
                "finished_at": datetime.utcnow(),
                "total_files": total_files,
                "success_count": success_count,
                "error_count": error_count,
                "details": sync_details,
            })

            await db.commit()

            logger.info(
                "Sync kb_id=%s finished: mode=%s status=%s files=%d ok=%d err=%d docs=%d",
                kb.id, sync_mode, job_status, total_files,
                success_count, error_count, total_doc_count,
            )

            return {
                "sync_log_id": sync_log_id,
                "status": job_status,
                "sync_mode": sync_mode,
                "total_files": total_files,
                "success_count": success_count,
                "error_count": error_count,
                "total_documents": total_doc_count,
                "total_slices": result.get("total_slice_count", 0),
            }

        except Exception as exc:
            logger.exception("Sync failed for KB %s", kb_id)
            await SyncService._finalize_failed_sync(db, sync_log_id, exc)
            return {
                "sync_log_id": sync_log_id,
                "status": "failed",
                "error": str(exc),
                "sync_mode": "unknown",
                "total_files": 0,
                "success_count": 0,
                "error_count": 0,
                "total_documents": 0,
                "total_slices": 0,
            }

        finally:
            if work_dir:
                GitSyncService.cleanup(work_dir)

    # ------------------------------------------------------------------
    # Full mode — same as original: delete all then re-import
    # ------------------------------------------------------------------

    @staticmethod
    async def _sync_full(
        db: AsyncSession,
        kb,
        repo_path: str,
        md_files: list[str],
        schema_hash: str,
        *,
        doc_field_types: dict[str, str] | None = None,
        slice_field_types: dict[str, str] | None = None,
    ) -> dict:
        deleted_slices = await SliceRepository.delete_by_kb_id(db, kb.id)
        deleted_docs = await DocumentRepository.delete_by_kb_id(db, kb.id)
        await db.commit()
        logger.info(
            "Sync kb_id=%s [full]: cleared prior data (documents=%s slices=%s)",
            kb.id, deleted_docs, deleted_slices,
        )

        details: list[dict] = []
        success_count = 0
        error_count = 0
        total_doc_count = 0
        total_slice_count = 0
        total_files = len(md_files)

        for idx, rel_path in enumerate(md_files, start=1):
            full_path = os.path.join(repo_path, rel_path)
            try:
                async with db.begin_nested():
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    content_hash = _compute_content_hash(content)
                    parsed = parse_document(
                        rel_path,
                        content,
                        doc_field_types=doc_field_types,
                        slice_field_types=slice_field_types,
                    )
                    doc_record = await _save_document(
                        db, kb, parsed, content_hash=content_hash,
                    )
                    slice_records = await _save_slices(db, kb, doc_record, parsed)

                    total_doc_count += 1
                    total_slice_count += len(slice_records)
                    success_count += 1
                    details.append({
                        "file": rel_path,
                        "status": "added",
                        "slice_count": len(slice_records),
                    })
                    logger.info(
                        "Sync kb_id=%s [full] %d/%d ok file=%s slices=%d",
                        kb.id, idx, total_files, rel_path, len(slice_records),
                    )
                await db.commit()
            except Exception as exc:
                error_count += 1
                details.append({"file": rel_path, "status": "error", "error": str(exc)})
                logger.error(
                    "Sync kb_id=%s [full] %d/%d FAILED file=%s: %s",
                    kb.id, idx, total_files, rel_path, exc,
                )
                try:
                    await db.rollback()
                except Exception:
                    pass

        return {
            "details": details,
            "success_count": success_count,
            "error_count": error_count,
            "total_doc_count": total_doc_count,
            "total_slice_count": total_slice_count,
            "added_count": success_count,
            "modified_count": 0,
            "unchanged_count": 0,
            "deleted_count": 0,
        }

    # ------------------------------------------------------------------
    # Incremental mode — only process changed files
    # ------------------------------------------------------------------

    @staticmethod
    async def _sync_incremental(
        db: AsyncSession,
        kb,
        repo_path: str,
        md_files: list[str],
        schema_hash: str,
        *,
        doc_field_types: dict[str, str] | None = None,
        slice_field_types: dict[str, str] | None = None,
    ) -> dict:
        # Build discovered hash map
        discovered: dict[str, str] = {}
        file_contents: dict[str, str] = {}
        for rel_path in md_files:
            full_path = os.path.join(repo_path, rel_path)
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            discovered[rel_path] = _compute_content_hash(content)
            file_contents[rel_path] = content

        existing = await DocumentRepository.get_hash_map_by_kb(db, kb.id)
        added, modified, unchanged, deleted = _classify_files(discovered, existing)

        logger.info(
            "Sync kb_id=%s [incremental]: added=%d modified=%d unchanged=%d deleted=%d",
            kb.id, len(added), len(modified), len(unchanged), len(deleted),
        )

        details: list[dict] = []
        success_count = 0
        error_count = 0
        total_slice_count = 0

        # Process ADDED files
        for rel_path in added:
            try:
                async with db.begin_nested():
                    parsed = parse_document(
                        rel_path,
                        file_contents[rel_path],
                        doc_field_types=doc_field_types,
                        slice_field_types=slice_field_types,
                    )
                    doc_record = await _save_document(
                        db, kb, parsed, content_hash=discovered[rel_path],
                    )
                    slices = await _save_slices(db, kb, doc_record, parsed)
                    total_slice_count += len(slices)
                    success_count += 1
                    details.append({
                        "file": rel_path, "status": "added",
                        "slice_count": len(slices),
                    })
                    logger.info(
                        "Sync kb_id=%s [incr] added file=%s slices=%d",
                        kb.id, rel_path, len(slices),
                    )
                await db.commit()
            except Exception as exc:
                error_count += 1
                details.append({"file": rel_path, "status": "error", "error": str(exc)})
                logger.error("Sync kb_id=%s [incr] add FAILED file=%s: %s", kb.id, rel_path, exc)
                try:
                    await db.rollback()
                except Exception:
                    pass

        # Process MODIFIED files
        for rel_path in modified:
            doc_id = existing[rel_path][0]
            try:
                async with db.begin_nested():
                    await SliceRepository.delete_by_document_id(db, doc_id)

                    doc = await DocumentRepository.get_by_id(db, doc_id)
                    parsed = parse_document(
                        rel_path,
                        file_contents[rel_path],
                        doc_field_types=doc_field_types,
                        slice_field_types=slice_field_types,
                    )

                    await DocumentRepository.update_document(db, doc, {
                        "title": _clip_str(parsed.title, _DOC_TITLE_MAX),
                        "description": parsed.description,
                        "source_url": _clip_str(parsed.source_url, _DOC_SOURCE_URL_MAX),
                        "markdown_content": parsed.markdown_content,
                        "doc_meta": parsed.doc_meta if parsed.doc_meta else None,
                        "toc": parsed.toc if parsed.toc else None,
                        "slice_count": len(parsed.slices),
                        "content_hash": discovered[rel_path],
                    })

                    slices = await _save_slices(db, kb, doc, parsed)
                    total_slice_count += len(slices)
                    success_count += 1
                    details.append({
                        "file": rel_path, "status": "modified",
                        "slice_count": len(slices),
                    })
                    logger.info(
                        "Sync kb_id=%s [incr] modified file=%s slices=%d",
                        kb.id, rel_path, len(slices),
                    )
                await db.commit()
            except Exception as exc:
                error_count += 1
                details.append({"file": rel_path, "status": "error", "error": str(exc)})
                logger.error("Sync kb_id=%s [incr] modify FAILED file=%s: %s", kb.id, rel_path, exc)
                try:
                    await db.rollback()
                except Exception:
                    pass

        # Process DELETED files
        for rel_path in deleted:
            doc_id = existing[rel_path][0]
            try:
                async with db.begin_nested():
                    await SliceRepository.delete_by_document_id(db, doc_id)
                    await DocumentRepository.delete_by_id(db, doc_id)
                    success_count += 1
                    details.append({"file": rel_path, "status": "deleted"})
                    logger.info("Sync kb_id=%s [incr] deleted file=%s", kb.id, rel_path)
                await db.commit()
            except Exception as exc:
                error_count += 1
                details.append({"file": rel_path, "status": "error", "error": str(exc)})
                logger.error("Sync kb_id=%s [incr] delete FAILED file=%s: %s", kb.id, rel_path, exc)
                try:
                    await db.rollback()
                except Exception:
                    pass

        # Unchanged files logged at debug
        for rel_path in unchanged:
            details.append({"file": rel_path, "status": "unchanged"})

        # Total remaining docs = unchanged + successfully added + successfully modified
        total_doc_count = (
            len(unchanged)
            + len([d for d in details if d["status"] == "added"])
            + len([d for d in details if d["status"] == "modified"])
        )

        return {
            "details": details,
            "success_count": success_count,
            "error_count": error_count,
            "total_doc_count": total_doc_count,
            "total_slice_count": total_slice_count,
            "added_count": len(added),
            "modified_count": len(modified),
            "unchanged_count": len(unchanged),
            "deleted_count": len(deleted),
        }

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    @staticmethod
    async def _finalize_failed_sync(
        db: AsyncSession, sync_log_id: int, exc: Exception
    ) -> None:
        """Mark sync log failed after rollback; never raises to caller."""
        try:
            await db.rollback()
        except Exception as rb_exc:
            logger.warning("Rollback after sync failure: %s", rb_exc)

        try:
            log_row = await SyncLogRepository.get_by_id(db, sync_log_id)
            if log_row:
                await SyncLogRepository.update(db, log_row, {
                    "status": "failed",
                    "finished_at": datetime.utcnow(),
                    "details": {"sync_mode": "unknown", "error": str(exc)},
                })
                await db.commit()
        except Exception as fin_exc:
            logger.error("Could not persist failed sync log %s: %s", sync_log_id, fin_exc)
            try:
                await db.rollback()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clip_str(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    if len(value) <= max_len:
        return value
    if max_len <= 3:
        return value[:max_len]
    return value[: max_len - 3] + "..."


async def _save_document(
    db: AsyncSession,
    kb,
    parsed: ParsedDocument,
    *,
    content_hash: str | None = None,
) -> object:
    """Save a parsed document to the documents table."""
    doc_data = {
        "knowledge_base_id": kb.id,
        "tenant_id": kb.tenant_id,
        "title": _clip_str(parsed.title, _DOC_TITLE_MAX),
        "description": parsed.description,
        "file_path": _clip_str(parsed.file_path or "", _DOC_FILE_PATH_MAX) or "unknown",
        "source_url": _clip_str(parsed.source_url, _DOC_SOURCE_URL_MAX),
        "markdown_content": parsed.markdown_content,
        "doc_meta": parsed.doc_meta if parsed.doc_meta else None,
        "toc": parsed.toc if parsed.toc else None,
        "slice_count": len(parsed.slices),
        "content_hash": content_hash,
    }
    return await DocumentRepository.create(db, doc_data)


async def _save_slices(
    db: AsyncSession,
    kb,
    doc_record,
    parsed: ParsedDocument,
) -> list:
    """Save parsed slices to the slices table, then generate embeddings."""
    if not parsed.slices:
        return []

    slice_items = []
    for s in parsed.slices:
        slice_items.append({
            "document_id": doc_record.id,
            "knowledge_base_id": kb.id,
            "tenant_id": kb.tenant_id,
            "content": s.content,
            "content_for_search": s.content_for_search or s.content,
            "toc_path": s.toc_path if s.toc_path else None,
            "toc_ancestors": s.toc_ancestors,
            "slice_meta": s.slice_meta if s.slice_meta else None,
            "doc_meta": parsed.doc_meta if parsed.doc_meta else None,
            "source_url": parsed.source_url,
            "markdown_url": f"/api/v1/knowledge-bases/{kb.id}/documents/{doc_record.id}/markdown",
            "slice_order": s.slice_order,
        })

    records = await SliceRepository.create_batch(db, slice_items)

    # Embedding in its own savepoint so failures don't poison the parent transaction
    try:
        async with db.begin_nested():
            await _generate_embeddings(db, records, kb_id=kb.id)
    except Exception as exc:
        logger.warning("Embedding generation failed (non-fatal): %s", exc)

    return records


async def _embed_batch_resilient(
    provider, texts: list[str]
) -> list[list[float]]:
    """Call embed API; on 413 split batch or truncate single oversized input."""
    if not texts:
        return []
    try:
        return await provider.embed_batch(texts)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 413:
            raise
        if len(texts) > 1:
            mid = len(texts) // 2
            first = await _embed_batch_resilient(provider, texts[:mid])
            second = await _embed_batch_resilient(provider, texts[mid:])
            return first + second
        t = texts[0]
        cap = min(len(t), _EMBED_MAX_CHARS_PER_TEXT)
        while cap >= 256:
            try:
                return await provider.embed_batch([t[:cap]])
            except httpx.HTTPStatusError as e2:
                if e2.response.status_code != 413:
                    raise
                cap //= 2
        logger.warning("Embedding skipped for oversized slice (413 after truncation)")
        raise


async def _generate_embeddings(
    db: AsyncSession,
    slice_records: list,
    *,
    kb_id: int | None = None,
) -> None:
    """Generate embedding vectors for slices and store them."""
    from app.libs.embedding.factory import create_embedding_provider
    from app.configs.settings import settings

    if not settings.SILICONFLOW_API_KEY:
        return

    total = len(slice_records)
    if total == 0:
        return

    provider = create_embedding_provider()
    texts = [
        (r.content_for_search or r.content)[:_EMBED_MAX_CHARS_PER_TEXT]
        for r in slice_records
    ]

    n_batches = (total + _EMBED_BATCH_SIZE - 1) // _EMBED_BATCH_SIZE
    log_prefix = f"kb_id={kb_id} " if kb_id is not None else ""
    logger.info(
        "%sembedding: %d slice(s), %d HTTP batch(es) of up to %d",
        log_prefix, total, n_batches, _EMBED_BATCH_SIZE,
    )

    for batch_num, i in enumerate(range(0, len(texts), _EMBED_BATCH_SIZE), start=1):
        batch_texts = texts[i:i + _EMBED_BATCH_SIZE]
        batch_records = slice_records[i:i + _EMBED_BATCH_SIZE]
        batch_len = len(batch_records)

        try:
            vectors = await _embed_batch_resilient(provider, batch_texts)
            for record, vector in zip(batch_records, vectors):
                record.embedding = vector
            await db.flush()
            logger.info(
                "%sembedding progress: batch %d/%d, slices %d-%d/%d (vectors flushed)",
                log_prefix, batch_num, n_batches, i + 1, i + batch_len, total,
            )
        except Exception as exc:
            logger.warning("Embedding batch %d failed: %s", i, exc)
