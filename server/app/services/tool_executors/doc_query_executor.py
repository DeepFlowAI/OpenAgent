"""
Doc query tool executor — queries documents (not slices) from knowledge base.
Response format: XML <document_results> per design spec.
"""
import logging
import re
from xml.sax.saxutils import escape

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.schemas.search import FilterCondition
from app.services.tool_executors.base import BaseToolExecutor, ToolContext

logger = logging.getLogger(__name__)


class DocQueryToolExecutor(BaseToolExecutor):

    async def execute(self, args: dict, config: dict, ctx: ToolContext) -> str:
        kb_id = config.get("knowledge_base_id")
        if not kb_id:
            return "<document_results>\nError: knowledge_base_id not configured for this tool.\n</document_results>"

        query = args.get("query", "").strip()
        llm_filter = args.get("filter", {})
        fixed_filters = config.get("fixed_filters", [])

        if not query and not llm_filter:
            return "<document_results>\nError: query or filter is required.\n</document_results>"

        is_search_mode = bool(query)
        limit = config.get("limit", 10) if is_search_mode else config.get("filter_limit", 50)
        meta_key = "search_response_meta_fields" if is_search_mode else "filter_response_meta_fields"
        response_meta = config.get(meta_key, {})

        logger.info(
            "Doc query — kb_id=%s, query=%s, mode=%s, limit=%d",
            kb_id, query or "(filter only)", "search" if is_search_mode else "filter", limit,
        )

        docs = await _query_documents(
            ctx.db, kb_id, query, fixed_filters, llm_filter, limit,
        )

        logger.info("Doc query — returned %d documents", len(docs))
        return _format_doc_xml(docs, response_meta)


async def _query_documents(
    db: AsyncSession,
    kb_id: int,
    query: str,
    fixed_filters: list[dict],
    llm_filter: dict,
    limit: int,
) -> list[Document]:
    """Query documents with optional keyword search + structured filters."""
    stmt = select(Document).where(Document.knowledge_base_id == kb_id)

    for fc in fixed_filters:
        if fc.get("level", "doc_meta") in ("doc_meta", "doc-meta"):
            stmt = stmt.where(
                Document.doc_meta[fc["field"]].astext == str(fc["value"])
                if fc.get("op") == "eq"
                else Document.doc_meta[fc["field"]].astext.contains(str(fc["value"]))
            )

    if llm_filter:
        if llm_filter.get("doc_ids"):
            doc_ids = [int(d) for d in llm_filter["doc_ids"]]
            stmt = stmt.where(Document.id.in_(doc_ids))
        for cond in llm_filter.get("doc_meta", []):
            field, op, value = cond["field"], cond["op"], cond["value"]
            if op in ("eq", "equals", "="):
                stmt = stmt.where(Document.doc_meta[field].astext == str(value))
            elif op in ("contains", "like"):
                stmt = stmt.where(Document.doc_meta[field].astext.contains(str(value)))
            elif op in ("ne", "!="):
                stmt = stmt.where(Document.doc_meta[field].astext != str(value))

    if query:
        keywords = _extract_keywords(query)
        logger.info("Doc query — keywords extracted: %s", keywords)
        if keywords:
            keyword_conds = []
            for kw in keywords:
                pattern = f"%{kw}%"
                keyword_conds.append(or_(
                    Document.title.ilike(pattern),
                    Document.description.ilike(pattern),
                ))
            stmt = stmt.where(or_(*keyword_conds))
        stmt = stmt.order_by(Document.id.desc())
    else:
        stmt = stmt.order_by(Document.id.desc())

    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())


def _format_doc_xml(docs: list[Document], response_meta: dict) -> str:
    """Format document results as XML per design spec."""
    if not docs:
        return "<document_results>\n</document_results>"

    doc_meta_fields = response_meta.get("doc_meta", [])
    extra_fields = response_meta.get("extra", [])

    lines = ["<document_results>", ""]
    for doc in docs:
        attrs = [f'doc_id="{doc.id}"']

        if doc.title:
            attrs.append(f'title="{escape(doc.title)}"')
        if doc.description:
            attrs.append(f'description="{escape(doc.description)}"')

        for field in doc_meta_fields:
            val = None
            if hasattr(doc, field):
                val = getattr(doc, field)
            elif doc.doc_meta:
                val = doc.doc_meta.get(field)
            if val is not None:
                attrs.append(f'{field}="{escape(str(val))}"')

        for field in extra_fields:
            if field == "toc" and doc.toc:
                flat = _flatten_toc(doc.toc)
                if flat:
                    attrs.append(f'toc="{escape(flat)}"')
            elif field == "source_url" and doc.source_url:
                attrs.append(f'source_url="{escape(doc.source_url)}"')

        attr_str = " ".join(attrs)
        lines.append(f"<doc {attr_str}>\n</doc>")
        lines.append("")

    lines.append("</document_results>")
    return "\n".join(lines)


def _flatten_toc(toc: list) -> str:
    """Flatten TOC tree into readable string."""
    parts: list[str] = []

    def _walk(nodes: list, depth: int = 0):
        for node in nodes:
            if isinstance(node, dict):
                title = node.get("title") or node.get("text", "")
                if title:
                    parts.append(title)
                children = node.get("children", [])
                if children:
                    _walk(children, depth + 1)
            elif isinstance(node, str):
                parts.append(node)

    _walk(toc)
    return " > ".join(parts)


_CJK_STOP_WORDS = set("的了是在我有和与就不人他这中大为上个国到说时要于也子以能会可出发对开着经公样都把好还多没因同主此前所")


def _extract_keywords(query: str) -> list[str]:
    """Split a Chinese/mixed query into meaningful keyword segments.

    Strategy: split on common delimiters and stop-words, keep segments >= 2 chars.
    Falls back to bigram sliding window for pure-CJK chunks.
    """
    tokens: list[str] = []

    parts = re.split(r'[,，。！？、；：\s·/\\|()（）【】\[\]{}""''\'\"]+', query)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        sub_parts = re.split(r'[的了是在与和]+', part)
        for sp in sub_parts:
            sp = sp.strip()
            if len(sp) >= 2:
                tokens.append(sp)

    if not tokens and len(query) >= 2:
        tokens = [query]

    seen: set[str] = set()
    unique: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    return unique
