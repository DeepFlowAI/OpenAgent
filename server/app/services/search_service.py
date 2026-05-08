"""
Search service — orchestrates BM25/Vector/Hybrid search + Reranker.
Aligned with AI搜索 api.md design spec.
"""
import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.search_repository import SearchRepository, highlight_text
from app.schemas.search import (
    SearchRequest, SearchResultItem, ScoresDetail, HighlightResult,
)

logger = logging.getLogger(__name__)


def _toc_ancestors_from_path(toc_path: Any) -> str | None:
    """Fallback when Slice.toc_ancestors column is NULL (legacy rows)."""
    if toc_path is None:
        return None
    try:
        seq = list(toc_path)
    except TypeError:
        return None
    if len(seq) <= 1:
        return None
    return " > ".join(str(x) for x in seq[:-1])


class SearchService:

    @staticmethod
    async def search(
        db: AsyncSession,
        kb_id: int,
        request: SearchRequest,
        subject_context: dict | None = None,
    ) -> dict:
        """Execute search pipeline: filter → permission deny → recall → fusion → reranker → paginate."""
        kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not kb or kb.status == "deleted":
            raise NotFoundError("Knowledge base not found")

        filter_conds = SearchService._build_filter_conditions(request)

        # Permission engine: append deny filters based on subject context
        from app.services.permission_engine import PermissionEngine
        deny_filters = await PermissionEngine.build_deny_filters(
            db, kb_id, subject_context
        )
        if deny_filters:
            filter_conds.extend(deny_filters)

        doc_ids = None
        if request.filter and request.filter.doc_ids:
            doc_ids = [int(d) for d in request.filter.doc_ids]

        mode = request.search.mode
        limit = request.pagination.limit
        offset = request.pagination.offset

        if mode == "bm25":
            items, total = await SearchService._bm25_search(
                db, kb_id, request.query, filter_conds, doc_ids, limit, offset
            )
        elif mode == "vector":
            items, total = await SearchService._vector_search(
                db, kb_id, request.query, filter_conds, doc_ids, limit, offset
            )
        elif mode == "hybrid":
            items, total = await SearchService._hybrid_search(
                db, kb_id, request.query, filter_conds, doc_ids, limit, offset, request
            )
        else:
            raise ValidationError(f"Unknown search mode: {mode}")

        if request.reranker.enabled and items:
            items = await SearchService._apply_reranker(
                request.query, items, request.reranker.top_n or limit,
                min_score=request.reranker.min_score,
            )

        if request.highlight.enabled:
            keywords = request.query.strip().split()
            for item in items:
                hl_text = highlight_text(
                    item["content"], keywords,
                    request.highlight.pre_tag, request.highlight.post_tag
                )
                item["highlight"] = {"content": hl_text}

        result_items = []
        for item in items:
            tp = item.get("toc_path")
            toc_a = item.get("toc_ancestors")
            if toc_a is None:
                toc_a = _toc_ancestors_from_path(tp)
            result_items.append(SearchResultItem(
                slice_id=item["slice_id"],
                doc_id=item["doc_id"],
                content=item["content"],
                toc_path=tp,
                toc_ancestors=toc_a,
                score=item.get("score", 0.0),
                scores=ScoresDetail(
                    bm25=item.get("bm25_score"),
                    vector=item.get("vector_score"),
                    reranker=item.get("reranker_score"),
                ),
                source_url=item.get("source_url"),
                markdown_url=item.get("markdown_url"),
                doc_meta=item.get("doc_meta"),
                slice_meta=item.get("slice_meta"),
                highlight=HighlightResult(content=item["highlight"]["content"])
                if item.get("highlight") else None,
            ))

        return {"total": total, "items": result_items}

    @staticmethod
    def _build_filter_conditions(request: SearchRequest) -> list:
        """Convert request filters to SQLAlchemy conditions."""
        from app.models.slice import Slice

        conditions = []
        if not request.filter:
            return conditions

        if request.filter.doc_meta:
            for cond in request.filter.doc_meta:
                conditions.append(
                    SearchRepository._build_filter_condition(Slice.doc_meta, cond)
                )
        if request.filter.slice_meta:
            for cond in request.filter.slice_meta:
                conditions.append(
                    SearchRepository._build_filter_condition(Slice.slice_meta, cond)
                )

        return conditions

    @staticmethod
    async def _bm25_search(
        db, kb_id, query, filter_conds, doc_ids, limit, offset
    ) -> tuple[list[dict], int]:
        items, total = await SearchRepository.keyword_search(
            db, kb_id, query, filter_conds, doc_ids, limit, offset
        )
        for item in items:
            item["score"] = item["bm25_score"]
        return items, total

    @staticmethod
    async def _vector_search(
        db, kb_id, query, filter_conds, doc_ids, limit, offset
    ) -> tuple[list[dict], int]:
        from app.libs.embedding.factory import create_embedding_provider

        provider = create_embedding_provider()
        query_vector = await provider.embed_text(query)

        items, total = await SearchRepository.vector_search(
            db, kb_id, query_vector, filter_conds, doc_ids, limit, offset
        )
        for item in items:
            item["score"] = item["vector_score"]
        return items, total

    @staticmethod
    async def _hybrid_search(
        db, kb_id, query, filter_conds, doc_ids, limit, offset, request
    ) -> tuple[list[dict], int]:
        from app.libs.embedding.factory import create_embedding_provider

        provider = create_embedding_provider()
        query_vector = await provider.embed_text(query)

        recall_limit = max(limit * 3, 50)

        bm25_items, bm25_total = await SearchRepository.keyword_search(
            db, kb_id, query, filter_conds, doc_ids, recall_limit, 0
        )
        vector_items, vector_total = await SearchRepository.vector_search(
            db, kb_id, query_vector, filter_conds, doc_ids, recall_limit, 0
        )

        bm25_weight = request.search.bm25.weight
        vector_weight = request.search.vector.weight

        bm25_scores = [i["bm25_score"] for i in bm25_items]
        vector_scores = [i["vector_score"] for i in vector_items]

        bm25_norm = _normalize_scores(bm25_scores)
        vector_norm = _normalize_scores(vector_scores)

        merged: dict[int, dict] = {}

        for i, item in enumerate(bm25_items):
            sid = item["slice_id"]
            item["bm25_score_norm"] = bm25_norm[i]
            merged[sid] = item

        for i, item in enumerate(vector_items):
            sid = item["slice_id"]
            if sid in merged:
                merged[sid]["vector_score"] = item["vector_score"]
                merged[sid]["vector_score_norm"] = vector_norm[i]
            else:
                item["vector_score_norm"] = vector_norm[i]
                item["bm25_score"] = 0.0
                item["bm25_score_norm"] = 0.0
                merged[sid] = item

        for item in merged.values():
            bm25_n = item.get("bm25_score_norm", 0.0)
            vector_n = item.get("vector_score_norm", 0.0)
            item["score"] = bm25_n * bm25_weight + vector_n * vector_weight

        sorted_items = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        total = max(bm25_total, vector_total)

        paginated = sorted_items[offset:offset + limit]
        return paginated, total

    @staticmethod
    async def _apply_reranker(
        query: str, items: list[dict], top_n: int,
        min_score: float | None = None,
    ) -> list[dict]:
        from app.libs.reranker.factory import create_reranker_provider

        provider = create_reranker_provider()
        documents = [item["content"] for item in items]

        try:
            results = await provider.rerank(query, documents, top_n=top_n)
        except Exception as exc:
            logger.error("Reranker failed: %s", exc)
            return items

        reranked = []
        for r in results[:top_n]:
            idx = r["index"]
            if idx < len(items):
                score = r["relevance_score"]
                if min_score is not None and score < min_score:
                    continue
                item = items[idx]
                item["reranker_score"] = score
                item["score"] = score
                reranked.append(item)

        return reranked


def _normalize_scores(scores: list[float]) -> list[float]:
    """Min-max normalize scores to [0, 1]."""
    if not scores:
        return []
    min_s = min(scores)
    max_s = max(scores)
    if max_s == min_s:
        return [1.0] * len(scores)
    return [(s - min_s) / (max_s - min_s) for s in scores]
