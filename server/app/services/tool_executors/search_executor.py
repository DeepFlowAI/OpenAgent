"""
Search tool executor — calls SearchService for slice-level knowledge base search.
Response format: XML <search_results> per design spec.
"""
import logging
from xml.sax.saxutils import escape

from app.schemas.search import (
    SearchRequest, SearchConfig, SearchFilter, FilterNode,
    RerankerConfig, PaginationConfig, BM25Config, VectorConfig,
)
from app.services.search_service import SearchService
from app.services.tool_executors.base import BaseToolExecutor, ToolContext

logger = logging.getLogger(__name__)


class SearchToolExecutor(BaseToolExecutor):

    async def execute(self, args: dict, config: dict, ctx: ToolContext) -> str:
        kb_id = config.get("knowledge_base_id")
        if not kb_id:
            return "<search_results>\nError: knowledge_base_id not configured for this tool.\n</search_results>"

        query = args.get("query", "").strip()
        if not query:
            return "<search_results>\nError: query is required.\n</search_results>"

        merged_filter = _merge_filters(
            config.get("fixed_filters", []),
            args.get("filter", {}),
        )

        search_mode = config.get("search_mode", "hybrid")
        weights = config.get("search_weights", {})
        bm25_weight = weights.get("bm25", 0.5)
        vector_weight = weights.get("vector", 0.5)

        reranker_cfg = config.get("reranker", {})
        reranker_enabled = reranker_cfg.get("enabled", False)
        reranker_top_n = reranker_cfg.get("top_n", None)
        reranker_min_score = reranker_cfg.get("min_score", None)

        pagination_cfg = config.get("pagination", {})
        limit = pagination_cfg.get("limit", config.get("limit", 10))

        request = SearchRequest(
            query=query,
            filter=merged_filter,
            search=SearchConfig(
                mode=search_mode,
                bm25=BM25Config(weight=bm25_weight),
                vector=VectorConfig(weight=vector_weight),
            ),
            reranker=RerankerConfig(enabled=reranker_enabled, top_n=reranker_top_n, min_score=reranker_min_score),
            pagination=PaginationConfig(limit=limit, offset=0),
        )

        logger.info(
            "Search tool — kb_id=%s, query=%s, mode=%s, "
            "bm25_weight=%.2f, vector_weight=%.2f, reranker=%s, limit=%d",
            kb_id, query, search_mode,
            bm25_weight, vector_weight, reranker_enabled, limit,
        )

        # Load conversation's customer context for permission engine
        subject_context = await _load_subject_context(ctx)

        result = await SearchService.search(ctx.db, kb_id, request, subject_context)
        items = result.get("items", [])

        # Category search: run each group independently, merge results
        cat_cfg = config.get("category_search", {})
        if cat_cfg.get("enabled") and cat_cfg.get("groups"):
            cat_items = await _run_category_search(
                ctx.db, kb_id, query, cat_cfg["groups"],
                config, args, search_mode, bm25_weight, vector_weight,
                reranker_enabled, reranker_top_n, reranker_min_score, limit,
                subject_context,
            )
            # Merge: deduplicate by slice_id, keep higher score
            seen = {item.slice_id: item for item in items}
            for ci in cat_items:
                if ci.slice_id not in seen or ci.score > seen[ci.slice_id].score:
                    seen[ci.slice_id] = ci
            items = sorted(seen.values(), key=lambda x: x.score, reverse=True)[:limit]

        logger.info("Search tool — returned %d items", len(items))

        response_meta = config.get("response_meta_fields", {})
        return _format_search_xml(items, response_meta)


async def _run_category_search(
    db, kb_id: int, query: str, groups: list[dict],
    config: dict, args: dict,
    search_mode: str, bm25_weight: float, vector_weight: float,
    reranker_enabled: bool, reranker_top_n: int | None,
    reranker_min_score: float | None, limit: int,
    subject_context: dict | None,
) -> list:
    """Run independent search per category group, merge and deduplicate.

    Per-group recall count derives from the main retrieval config:
    - If reranker enabled: each group recalls reranker_top_n items
    - Otherwise: each group recalls `limit` items

    After merging all groups:
    - If reranker enabled: rerank merged set, take `limit`
    - Otherwise: sort by score, take `limit`
    """
    per_group_recall = reranker_top_n if reranker_enabled and reranker_top_n else limit

    async def _search_one_group(group: dict):
        group_filters = group.get("filters", [])
        group_fixed = config.get("fixed_filters", []) + [
            {"level": f.get("level", "doc_meta"), "field": f["field"], "op": f["op"], "value": f["value"]}
            for f in group_filters
            if f.get("field") and f.get("op")
        ]
        merged_filter = _merge_filters(group_fixed, args.get("filter", {}))

        req = SearchRequest(
            query=query,
            filter=merged_filter,
            search=SearchConfig(
                mode=search_mode,
                bm25=BM25Config(weight=bm25_weight),
                vector=VectorConfig(weight=vector_weight),
            ),
            reranker=RerankerConfig(enabled=False),
            pagination=PaginationConfig(limit=per_group_recall, offset=0),
        )
        result = await SearchService.search(db, kb_id, req, subject_context)
        return result.get("items", [])

    # Run groups sequentially — async sessions are not safe for concurrent use
    seen: dict[int, object] = {}
    for group in groups:
        try:
            group_items = await _search_one_group(group)
        except Exception as exc:
            logger.error("Category group search failed: %s", exc)
            continue
        for item in group_items:
            if item.slice_id not in seen or item.score > seen[item.slice_id].score:
                seen[item.slice_id] = item

    merged_items = list(seen.values())

    if reranker_enabled and merged_items:
        from app.libs.reranker.factory import create_reranker_provider

        provider = create_reranker_provider()
        documents = [item.content for item in merged_items]
        try:
            results = await provider.rerank(query, documents, top_n=limit)
            reranked = []
            for r in results[:limit]:
                idx = r["index"]
                if idx < len(merged_items):
                    score = r["relevance_score"]
                    if reranker_min_score is not None and score < reranker_min_score:
                        continue
                    item = merged_items[idx]
                    item = item.model_copy(update={
                        "score": score,
                        "scores": item.scores.model_copy(update={"reranker": score}),
                    })
                    reranked.append(item)
            return reranked
        except Exception as exc:
            logger.error("Category search reranker failed: %s", exc)

    # No reranker: sort by score, take limit
    merged_items.sort(key=lambda x: x.score, reverse=True)
    return merged_items[:limit]


def _parse_filter_nodes(raw) -> list[FilterNode]:
    """Parse a list-or-single raw filter value into a list of FilterNode."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [FilterNode.model_validate(raw)]
    if isinstance(raw, list):
        return [
            FilterNode.model_validate(v) if isinstance(v, dict) else v
            for v in raw
        ]
    return []


def _merge_filters(
    fixed_filters: list[dict],
    llm_filter: dict,
) -> SearchFilter | None:
    """Merge fixed_filters (from tool config) with LLM-provided filter using AND."""
    doc_meta_conds: list[FilterNode] = []
    slice_meta_conds: list[FilterNode] = []
    doc_ids: list[str] | None = None

    for fc in fixed_filters:
        level = fc.get("level", "doc_meta")
        cond = FilterNode(field=fc["field"], op=fc["op"], value=fc["value"])
        if level in ("slice_meta", "slice-meta"):
            slice_meta_conds.append(cond)
        else:
            doc_meta_conds.append(cond)

    if llm_filter:
        doc_meta_conds.extend(_parse_filter_nodes(llm_filter.get("doc_meta")))
        slice_meta_conds.extend(_parse_filter_nodes(llm_filter.get("slice_meta")))
        if llm_filter.get("doc_ids"):
            llm_doc_ids = [str(d) for d in llm_filter["doc_ids"]]
            doc_ids = llm_doc_ids if doc_ids is None else list(set(doc_ids) & set(llm_doc_ids))

    if not doc_meta_conds and not slice_meta_conds and not doc_ids:
        return None

    return SearchFilter(
        doc_ids=doc_ids,
        doc_meta=doc_meta_conds or None,
        slice_meta=slice_meta_conds or None,
    )


async def _load_subject_context(ctx: ToolContext) -> dict | None:
    """Load conversation's customer context as subject context for permission engine."""
    from app.repositories.conversation_repository import ConversationRepository

    conv = await ConversationRepository.get_by_id(ctx.db, ctx.conversation_id)
    if not conv:
        return None

    subject = {}
    if conv.external_user_id:
        subject["external_user_id"] = conv.external_user_id
    if conv.display_name:
        subject["display_name"] = conv.display_name
    if conv.email:
        subject["email"] = conv.email
    if conv.source:
        subject["source"] = conv.source
    if conv.channel_id:
        subject["channel_id"] = conv.channel_id
    if conv.channel_source:
        subject["channel_source"] = conv.channel_source

    # metadata is the key namespace for permission rule user conditions
    metadata = conv.metadata_ if hasattr(conv, "metadata_") else {}
    subject["metadata"] = metadata or {}

    return subject


def _format_search_xml(items: list, response_meta: dict) -> str:
    """Format search results as XML per design spec."""
    if not items:
        return "<search_results>\n</search_results>"

    doc_meta_fields = response_meta.get("doc_meta", [])
    slice_meta_fields = response_meta.get("slice_meta", [])
    extra_fields = response_meta.get("extra", [])

    lines = ["<search_results>", ""]
    for item in items:
        attrs = [
            f'doc_id="{item.doc_id}"',
            f'slice_id="{item.slice_id}"',
        ]

        if item.doc_meta:
            for field in doc_meta_fields:
                val = item.doc_meta.get(field)
                if val is not None:
                    attrs.append(f'{field}="{escape(str(val))}"')

        if item.slice_meta:
            for field in slice_meta_fields:
                val = item.slice_meta.get(field)
                if val is not None:
                    attrs.append(f'{field}="{escape(str(val))}"')

        for field in extra_fields:
            val = getattr(item, field, None)
            if val is not None:
                if isinstance(val, list):
                    val = " > ".join(str(v) for v in val)
                attrs.append(f'{field}="{escape(str(val))}"')

        attr_str = " ".join(attrs)
        content = escape(item.content) if item.content else ""
        lines.append(f"<result {attr_str}>\n{content}\n</result>")
        lines.append("")

    lines.append("</search_results>")
    return "\n".join(lines)
