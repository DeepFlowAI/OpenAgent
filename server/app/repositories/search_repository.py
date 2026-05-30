"""
Search repository — BM25 (ILIKE) + vector (pgvector) + OData-aligned JSONB filter system.
"""
import re
import logging
from typing import Any

from sqlalchemy import select, func, and_, or_, text, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.slice import Slice
from app.schemas.search import FilterNode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OData filter normalization
# ---------------------------------------------------------------------------

_OP_ALIASES: dict[str, str] = {
    "neq": "ne",
    "!=": "ne",
    "gte": "ge",
    "lte": "le",
}


def normalize_filter_node(node: FilterNode) -> FilterNode:
    """Normalize non-OData operators to OData-standard equivalents (idempotent)."""
    if node.fn:
        return node

    op = node.op
    if not op:
        return node

    # --- recurse into logic / lambda children first ---
    if op in ("and", "or") and isinstance(node.value, list):
        return FilterNode(
            op=op,
            value=[
                normalize_filter_node(v) if isinstance(v, FilterNode) else v
                for v in node.value
            ],
        )
    if op == "not" and isinstance(node.value, FilterNode):
        return FilterNode(op="not", value=normalize_filter_node(node.value))
    if op in ("any", "all") and node.predicate:
        return FilterNode(
            op=op, field=node.field, var=node.var,
            predicate=normalize_filter_node(node.predicate),
        )

    # --- simple alias mapping (neq→ne, gte→ge, lte→le) ---
    if op in _OP_ALIASES:
        return FilterNode(field=node.field, op=_OP_ALIASES[op], value=node.value)

    # --- compound expansions ---
    if op in ("not_in", "nin", "notIn"):
        return FilterNode(
            op="not",
            value=FilterNode(field=node.field, op="in", value=node.value),
        )

    if op in ("between", "betweenInclusive"):
        if isinstance(node.value, list) and len(node.value) == 2:
            return FilterNode(
                op="and",
                value=[
                    FilterNode(field=node.field, op="ge", value=node.value[0]),
                    FilterNode(field=node.field, op="le", value=node.value[1]),
                ],
            )
        return node

    if op == "betweenExclusive":
        if isinstance(node.value, list) and len(node.value) == 2:
            return FilterNode(
                op="and",
                value=[
                    FilterNode(field=node.field, op="gt", value=node.value[0]),
                    FilterNode(field=node.field, op="lt", value=node.value[1]),
                ],
            )
        return node

    if op in ("like", "ilike"):
        val = str(node.value) if node.value is not None else ""
        if val.startswith("%") and val.endswith("%") and len(val) > 2:
            return FilterNode(fn="contains", field=node.field, value=val[1:-1])
        if val.endswith("%") and not val.startswith("%"):
            return FilterNode(fn="startswith", field=node.field, value=val[:-1])
        if val.startswith("%") and not val.endswith("%"):
            return FilterNode(fn="endswith", field=node.field, value=val[1:])
        return FilterNode(fn="matchesPattern", field=node.field, value=val)

    if op == "contains":
        # If value is a comma-separated string like "a,b,c", split into list
        # and treat as contains_any (match any one of the values).
        value = node.value
        if isinstance(value, str) and "," in value:
            values = [v.strip() for v in value.split(",") if v.strip()]
            return FilterNode(
                op="or",
                value=[
                    FilterNode(
                        op="any", field=node.field, var="x",
                        predicate=FilterNode(field="x", op="eq", value=v),
                    )
                    for v in values
                ],
            )
        return FilterNode(
            op="any", field=node.field, var="x",
            predicate=FilterNode(field="x", op="eq", value=value),
        )

    if op == "contains_all":
        values = node.value if isinstance(node.value, list) else [node.value]
        return FilterNode(
            op="and",
            value=[
                FilterNode(
                    op="any", field=node.field, var="x",
                    predicate=FilterNode(field="x", op="eq", value=v),
                )
                for v in values
            ],
        )

    if op == "contains_any":
        values = node.value if isinstance(node.value, list) else [node.value]
        return FilterNode(
            op="or",
            value=[
                FilterNode(
                    op="any", field=node.field, var="x",
                    predicate=FilterNode(field="x", op="eq", value=v),
                )
                for v in values
            ],
        )

    # Older console builds serialized multi selections as one comma-separated
    # string ("a,b,c"). Split them before SQL generation so each value matches
    # independently.
    if op in ("in", "has_any", "has_all"):
        val = node.value
        if isinstance(val, str) and "," in val:
            parts = [p.strip() for p in val.split(",") if p.strip()]
            return FilterNode(field=node.field, op=node.op, value=parts)

    return node


# ---------------------------------------------------------------------------
# SQLAlchemy WHERE-clause builder (operates on *normalized* AST)
# ---------------------------------------------------------------------------

def _escape_like(val: str) -> str:
    """Escape SQL LIKE special characters."""
    return val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _to_jsonb_text(value: Any) -> str:
    """Convert a Python scalar to its PostgreSQL ``jsonb ->> 'k'`` representation.

    This must match what PostgreSQL returns from ``jsonb ->>`` so that
    ``json_field.astext == _to_jsonb_text(value)`` actually matches.

    Notably:
      * JSON boolean ``true`` / ``false`` is rendered lowercase by ``->>``,
        but ``str(True)`` / ``str(False)`` in Python is ``"True"`` / ``"False"``.
        Without this normalization, ``has_fragrance == false`` filters never
        match any row.
      * JSON ``null`` becomes SQL NULL via ``->>`` — equality should not match
        ``"None"``; callers should use a dedicated null check, but we still
        avoid emitting the string ``"None"`` here.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _build_clause(column, node: FilterNode):
    """Build a SQLAlchemy WHERE clause from a normalized OData FilterNode."""

    # --- string function node ---
    if node.fn:
        return _build_fn_clause(column, node)

    op = node.op
    if not op:
        logger.warning("FilterNode has neither op nor fn, returning true")
        return text("true")

    # --- logic nodes ---
    if op == "and":
        children = node.value if isinstance(node.value, list) else []
        clauses = [_build_clause(column, v) for v in children if isinstance(v, FilterNode)]
        return and_(*clauses) if clauses else text("true")

    if op == "or":
        children = node.value if isinstance(node.value, list) else []
        clauses = [_build_clause(column, v) for v in children if isinstance(v, FilterNode)]
        return or_(*clauses) if clauses else text("false")

    if op == "not":
        if isinstance(node.value, FilterNode):
            return ~_build_clause(column, node.value)
        return text("true")

    # --- collection lambda (any / all) ---
    if op in ("any", "all"):
        return _build_lambda_clause(column, node)

    # --- leaf comparison ---
    if not node.field:
        logger.warning("Comparison FilterNode missing 'field'")
        return text("true")

    json_field = column[node.field]
    value = node.value

    if op == "eq":
        return json_field.astext == _to_jsonb_text(value)
    if op == "ne":
        return json_field.astext != _to_jsonb_text(value)
    if op == "gt":
        return cast(json_field.astext, Float) > float(value)
    if op == "ge":
        return cast(json_field.astext, Float) >= float(value)
    if op == "lt":
        return cast(json_field.astext, Float) < float(value)
    if op == "le":
        return cast(json_field.astext, Float) <= float(value)
    if op == "in":
        if isinstance(value, list):
            scalar_match = json_field.astext.in_([_to_jsonb_text(v) for v in value])
            array_match = or_(*[
                column.op("@>")(
                    func.jsonb_build_object(node.field, func.jsonb_build_array(v))
                )
                for v in value
            ])
            return or_(scalar_match, array_match)
        return json_field.astext == _to_jsonb_text(value)

    if op == "has_any":
        # JSONB array field contains ANY of the given values.
        # e.g. doc_meta->'tags' @> '["a"]' OR doc_meta->'tags' @> '["b"]'
        # Also handles scalar field: doc_meta->>'tags' IN ('a','b')
        vals = value if isinstance(value, list) else [value]
        array_clauses = [
            column.op("@>")(
                func.jsonb_build_object(node.field, func.jsonb_build_array(v))
            )
            for v in vals
        ]
        scalar_match = json_field.astext.in_([_to_jsonb_text(v) for v in vals])
        return or_(scalar_match, *array_clauses)

    if op == "has_all":
        # JSONB array field contains ALL of the given values.
        # e.g. doc_meta->'tags' @> '["a","b"]'
        # Also handles scalar: only matches if value list is a single item equal to the field.
        vals = value if isinstance(value, list) else [value]
        array_match = column.op("@>")(
            func.jsonb_build_object(node.field, func.cast(
                func.jsonb_build_array(*vals), column.type,
            ))
        )
        if len(vals) == 1:
            return or_(json_field.astext == _to_jsonb_text(vals[0]), array_match)
        return array_match

    logger.warning("Unknown filter op after normalization: %s", op)
    return text("true")


def _build_fn_clause(column, node: FilterNode):
    """Build WHERE clause for OData string function nodes."""
    fn = node.fn
    json_field = column[node.field]
    val = str(node.value) if node.value is not None else ""

    if fn == "contains":
        return json_field.astext.like(f"%{_escape_like(val)}%")
    if fn == "startswith":
        return json_field.astext.like(f"{_escape_like(val)}%")
    if fn == "endswith":
        return json_field.astext.like(f"%{_escape_like(val)}")
    if fn == "matchesPattern":
        return json_field.astext.op("~")(val)

    logger.warning("Unknown filter function: %s", fn)
    return text("true")


def _build_lambda_clause(column, node: FilterNode):
    """Build WHERE clause for collection lambda (any/all) on JSONB array fields."""
    if not node.field or not node.predicate:
        logger.warning("Lambda FilterNode missing field or predicate")
        return text("true")

    pred = node.predicate

    if pred.op == "eq":
        return column.op("@>")(
            func.jsonb_build_object(node.field, func.jsonb_build_array(pred.value))
        )
    if pred.op == "ne":
        return ~column.op("@>")(
            func.jsonb_build_object(node.field, func.jsonb_build_array(pred.value))
        )
    if pred.op == "in" and isinstance(pred.value, list):
        clauses = [
            column.op("@>")(
                func.jsonb_build_object(node.field, func.jsonb_build_array(v))
            )
            for v in pred.value
        ]
        if node.op == "all":
            return and_(*clauses) if clauses else text("true")
        return or_(*clauses) if clauses else text("false")

    logger.warning("Unsupported lambda predicate op: %s", pred.op)
    return text("true")


class SearchRepository:

    @staticmethod
    def _build_filter_condition(column, node: FilterNode):
        """Build SQLAlchemy WHERE clause from a FilterNode (auto-normalizes)."""
        return _build_clause(column, normalize_filter_node(node))

    @staticmethod
    async def keyword_search(
        db: AsyncSession,
        kb_id: int,
        query: str,
        filter_conditions: list | None = None,
        doc_ids: list[int] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """BM25-style keyword search using ILIKE + JSONB filters."""
        conditions = [Slice.knowledge_base_id == kb_id]

        if doc_ids:
            conditions.append(Slice.document_id.in_(doc_ids))

        if filter_conditions:
            conditions.extend(filter_conditions)

        keywords = query.strip().split()
        if keywords:
            keyword_conds = []
            for kw in keywords:
                pattern = f"%{kw}%"
                keyword_conds.append(
                    or_(
                        Slice.content.ilike(pattern),
                        Slice.content_for_search.ilike(pattern),
                    )
                )
            conditions.append(and_(*keyword_conds))

        total_result = await db.execute(
            select(func.count()).select_from(Slice).where(*conditions)
        )
        total = total_result.scalar_one()

        result = await db.execute(
            select(Slice)
            .where(*conditions)
            .order_by(Slice.slice_order.asc())
            .offset(offset)
            .limit(limit)
        )
        slices = list(result.scalars().all())

        items = []
        for s in slices:
            score = _compute_keyword_score(s.content_for_search or s.content, keywords)
            items.append({
                "slice_id": s.id,
                "doc_id": s.document_id,
                "content": s.content,
                "toc_path": s.toc_path,
                "toc_ancestors": s.toc_ancestors,
                "slice_meta": s.slice_meta,
                "doc_meta": s.doc_meta,
                "source_url": s.source_url,
                "markdown_url": s.markdown_url,
                "bm25_score": score,
            })

        items.sort(key=lambda x: x["bm25_score"], reverse=True)
        return items, total

    @staticmethod
    async def vector_search(
        db: AsyncSession,
        kb_id: int,
        query_vector: list[float],
        filter_conditions: list | None = None,
        doc_ids: list[int] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Vector similarity search using pgvector cosine distance."""
        conditions = [
            Slice.knowledge_base_id == kb_id,
            Slice.embedding.isnot(None),
        ]

        if doc_ids:
            conditions.append(Slice.document_id.in_(doc_ids))

        if filter_conditions:
            conditions.extend(filter_conditions)

        total_result = await db.execute(
            select(func.count()).select_from(Slice).where(*conditions)
        )
        total = total_result.scalar_one()

        if total == 0:
            return [], 0

        from pgvector.sqlalchemy import Vector
        vector_literal = text(
            f"'{[float(v) for v in query_vector]}'::vector"
        )
        distance_expr = Slice.embedding.cosine_distance(vector_literal)

        result = await db.execute(
            select(
                Slice.id,
                Slice.document_id,
                Slice.content,
                Slice.toc_path,
                Slice.toc_ancestors,
                Slice.slice_meta,
                Slice.doc_meta,
                Slice.source_url,
                Slice.markdown_url,
                distance_expr.label("distance"),
            )
            .where(*conditions)
            .order_by(distance_expr.asc())
            .offset(offset)
            .limit(limit)
        )

        items = []
        for row in result:
            sim = max(1.0 - float(row.distance), 0.0) if row.distance is not None else 0.0
            items.append({
                "slice_id": row.id,
                "doc_id": row.document_id,
                "content": row.content,
                "toc_path": row.toc_path,
                "toc_ancestors": row.toc_ancestors,
                "slice_meta": row.slice_meta,
                "doc_meta": row.doc_meta,
                "source_url": row.source_url,
                "markdown_url": row.markdown_url,
                "vector_score": sim,
            })

        return items, total


def _compute_keyword_score(text_content: str, keywords: list[str]) -> float:
    """Simple TF-based scoring for BM25-style ranking."""
    if not text_content or not keywords:
        return 0.0
    text_lower = text_content.lower()
    total = 0
    for kw in keywords:
        total += text_lower.count(kw.lower())
    return min(total / max(len(keywords), 1), 10.0)


def highlight_text(text_content: str, keywords: list[str], pre_tag: str, post_tag: str) -> str:
    """Wrap keyword occurrences with custom highlight tags."""
    result = text_content
    for kw in keywords:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        result = pattern.sub(f"{pre_tag}{kw}{post_tag}", result)
    return result
