"""
Public Help Center data access — visitor-facing reads with doc-meta filtering.

This repository handles only the read paths exposed by the visitor site. The
write paths live in `help_center_repository` / `help_center_tab_repository`.
"""
import re
from datetime import date
from typing import Any, Literal

from sqlalchemy import Date, Numeric, case, cast, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.document import Document
from app.models.help_center import HelpCenter
from app.models.help_center_tab import HelpCenterTab


_ValueKind = Literal["bool", "number", "date", "text"]

# SQL-side guard: shape only — the JSONB-extracted text must look like an
# ISO date with valid month (01-12) and day (01-31) before we attempt to
# CAST it to a Postgres `date`. This still admits calendar-impossible
# strings like "2026-02-31" or "2025-04-31" — those reflect corrupt
# user-stored data and would surface as a query error. Validating the
# filter VALUE (which we control via Pydantic + `_classify`) below is the
# main defence; the regex here only narrows the surface area for surprises
# coming from the documents table.
_ISO_DATE_RE = re.compile(
    r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"
)


def _stringify(value: Any) -> str:
    """Convert a Python value into the textual form a JSONB `->>` extraction
    produces. PostgreSQL serialises booleans as `true` / `false`, integers and
    floats as their Python `str()` form."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _is_iso_date(value: Any) -> bool:
    """True iff `value` is a string parseable by `date.fromisoformat`. We
    avoid a regex prefilter here because `fromisoformat` already enforces
    YYYY-MM-DD shape AND calendar validity (rejects e.g. 2026-02-31)."""
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _classify(value: Any) -> _ValueKind:
    """Infer a comparison kind from a single Python value. Order matters:
    `bool` is a subclass of `int` so it must be checked first.

    Invalid date strings fall through to `text` so the caller never blows up
    on `date.fromisoformat()` — they degrade to a (harmless) textual
    comparison instead of a 500 on the visitor API."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if _is_iso_date(value):
        return "date"
    return "text"


def _classify_list(values: list[Any]) -> _ValueKind:
    """Infer the kind for an `in` filter. Falls back to `text` if elements
    are mixed kinds OR any element fails strict validation, so `in` always
    has a safe textual interpretation."""
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "text"
    kinds = {_classify(v) for v in non_null}
    if len(kinds) == 1:
        return next(iter(kinds))
    return "text"


def _build_filter_clause(
    field: str, op: str, value: Any
) -> ColumnElement[bool]:
    """Translate one `{field, op, value}` filter into a SQL WHERE clause
    against `documents.doc_meta` JSONB.

    Comparison kind is inferred from the Python type of `value`:
      * bool         → typeof guard + textual `true`/`false` match
      * int / float  → typeof guard + ::numeric cast (correct ordering)
      * ISO date str → regex guard  + ::date    cast (correct ordering)
      * other str    → plain textual comparison

    Unknown ops fall through to `false()` so an invalid filter fails safe
    instead of returning the entire knowledge base.
    """
    text_expr = Document.doc_meta[field].astext
    json_expr = Document.doc_meta[field]

    if op == "in":
        if not isinstance(value, list) or len(value) == 0:
            return false()
        kind = _classify_list(value)
        if kind == "number":
            return case(
                (
                    func.jsonb_typeof(json_expr) == "number",
                    cast(text_expr, Numeric).in_([float(v) for v in value]),
                ),
                else_=False,
            )
        if kind == "date":
            rhs_dates = [date.fromisoformat(v) for v in value]
            return case(
                (
                    text_expr.op("~")(_ISO_DATE_RE.pattern),
                    cast(text_expr, Date).in_(rhs_dates),
                ),
                else_=False,
            )
        # bool / text both fall back to stringified equality membership.
        return text_expr.in_([_stringify(v) for v in value])

    kind = _classify(value)

    if kind == "bool":
        # eq / ne only — operators were validated upstream by the schema.
        match = text_expr == _stringify(value)
        guarded = case(
            (func.jsonb_typeof(json_expr) == "boolean", match),
            else_=False,
        )
        if op == "eq":
            return guarded
        if op == "ne":
            return or_(text_expr.is_(None), ~guarded)
        return false()

    if kind == "number":
        casted = cast(text_expr, Numeric)
        rhs = float(value)
        cmp_map = {
            "eq": casted == rhs,
            "ne": casted != rhs,
            "gt": casted > rhs,
            "ge": casted >= rhs,
            "lt": casted < rhs,
            "le": casted <= rhs,
        }
        if op not in cmp_map:
            return false()
        guarded = case(
            (func.jsonb_typeof(json_expr) == "number", cmp_map[op]),
            else_=False,
        )
        if op == "ne":
            # `ne` should also keep docs missing the field altogether.
            return or_(text_expr.is_(None), guarded)
        return guarded

    if kind == "date":
        casted = cast(text_expr, Date)
        rhs = date.fromisoformat(value)
        cmp_map = {
            "eq": casted == rhs,
            "ne": casted != rhs,
            "gt": casted > rhs,
            "ge": casted >= rhs,
            "lt": casted < rhs,
            "le": casted <= rhs,
        }
        if op not in cmp_map:
            return false()
        guarded = case(
            (text_expr.op("~")(_ISO_DATE_RE.pattern), cmp_map[op]),
            else_=False,
        )
        if op == "ne":
            return or_(text_expr.is_(None), guarded)
        return guarded

    # Plain text path: keep prior behaviour.
    if op == "eq":
        return text_expr == _stringify(value)
    if op == "ne":
        return or_(text_expr.is_(None), text_expr != _stringify(value))
    # gt/ge/lt/le on a text-typed field is meaningless lexically; the
    # frontend doesn't expose these for keyword/text/enum so failing safe
    # is the correct behaviour.
    return false()


def _apply_fixed_filters(stmt, fixed_filters: list[dict] | None):
    """Append all fixed filter conditions (AND) to the given select stmt."""
    if not fixed_filters:
        return stmt
    clauses = [
        _build_filter_clause(f["field"], f["op"], f.get("value"))
        for f in fixed_filters
        if isinstance(f, dict) and "field" in f and "op" in f
    ]
    if not clauses:
        return stmt
    return stmt.where(*clauses)


class PublicHelpCenterRepository:

    @staticmethod
    async def get_by_public_slug(
        db: AsyncSession, public_slug: str
    ) -> HelpCenter | None:
        """Resolve a Help Center by its public slug. The slug is globally
        unique (enforced by `uq_help_centers_public_slug`) so this returns
        at most one row regardless of tenant."""
        result = await db.execute(
            select(HelpCenter).where(HelpCenter.public_slug == public_slug)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_tabs(
        db: AsyncSession, help_center_id: int
    ) -> list[HelpCenterTab]:
        result = await db.execute(
            select(HelpCenterTab)
            .where(HelpCenterTab.help_center_id == help_center_id)
            .order_by(HelpCenterTab.sort_order.asc(), HelpCenterTab.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_tab_by_slug(
        db: AsyncSession, help_center_id: int, tab_slug: str
    ) -> HelpCenterTab | None:
        result = await db.execute(
            select(HelpCenterTab).where(
                HelpCenterTab.help_center_id == help_center_id,
                HelpCenterTab.tab_slug == tab_slug,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_docs_for_tab(
        db: AsyncSession,
        tab: HelpCenterTab,
        page: int,
        per_page: int,
    ) -> tuple[list[Document], int]:
        base = select(Document).where(
            Document.knowledge_base_id == tab.knowledge_base_id
        )
        base = _apply_fixed_filters(base, tab.fixed_filters)

        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await db.execute(total_stmt)).scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            base.order_by(Document.file_path.asc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_doc_by_path_for_tab(
        db: AsyncSession, tab: HelpCenterTab, file_path: str
    ) -> Document | None:
        """Find a doc by `(knowledge_base_id, file_path)` AND verify it's
        included in the tab's fixed-filter set. Returns None on any miss."""
        stmt = select(Document).where(
            Document.knowledge_base_id == tab.knowledge_base_id,
            Document.file_path == file_path,
        )
        stmt = _apply_fixed_filters(stmt, tab.fixed_filters)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all_docs_for_sitemap(
        db: AsyncSession, tab: HelpCenterTab
    ) -> list[Document]:
        """Return ALL docs for a tab (no pagination) — sitemap consumer.
        Spec 0.9 allows up to 50k URLs; we don't paginate for now."""
        stmt = select(Document).where(
            Document.knowledge_base_id == tab.knowledge_base_id
        )
        stmt = _apply_fixed_filters(stmt, tab.fixed_filters)
        stmt = stmt.order_by(Document.file_path.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())
