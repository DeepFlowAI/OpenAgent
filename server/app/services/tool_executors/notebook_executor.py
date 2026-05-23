"""
Notebook tool executor — manages a session-scoped scratch notebook.
Supports add/remove operations. State is rebuilt from conversation_step records.
"""
import logging
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from sqlalchemy import select

from app.models.conversation_step import ConversationStep
from app.models.document import Document
from app.models.slice import Slice
from app.services.tool_executors.base import BaseToolExecutor, ToolContext

logger = logging.getLogger(__name__)


NOTEBOOK_EMPTY_OUTPUT = "<notebook>\n</notebook>"


@dataclass
class NotebookEntry:
    id: str
    type: str
    attrs: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    text: str | None = None


class NotebookToolExecutor(BaseToolExecutor):

    async def execute(self, args: dict, config: dict, ctx: ToolContext) -> str:
        action = args.get("action", "").lower()
        items = args.get("items", [])

        if action not in ("add", "remove"):
            return (
                '<notebook_response action="error">'
                'Unsupported action. Use "add" or "remove".'
                '</notebook_response>'
            )

        if not items:
            return f'<notebook_response action="{action}">No items provided.</notebook_response>'

        entries, next_note_number = await load_notebook_entries(ctx)
        if action == "add":
            added = await _add_items(entries, items, ctx, next_note_number)
            logger.info(
                "Notebook add — %d items, current_total=%d", added, len(entries)
            )
            return _response("add", f"Added {added} item(s) to notebook.", len(entries))

        removed = _remove_items(entries, items)
        logger.info(
            "Notebook remove — %d items, current_total=%d", removed, len(entries)
        )
        if removed == 0:
            return _response("remove", "No matching items found.", len(entries))
        return _response("remove", f"Removed {removed} item(s) from notebook.", len(entries))


async def render_notebook_output(ctx: ToolContext) -> str:
    """Render the current notebook state as the tool_notebook_output variable."""
    entries, _ = await load_notebook_entries(ctx)
    return format_notebook_output(entries)


async def load_notebook_entries(
    ctx: ToolContext,
    *,
    before_step_order: int | None = None,
) -> tuple[list[NotebookEntry], int]:
    """Fold notebook tool_call steps into the current notebook state."""
    entries: list[NotebookEntry] = []
    next_note_number = 1
    steps = await _load_notebook_steps(ctx, before_step_order=before_step_order)

    for step in steps:
        args = step.tool_arguments or {}
        action = str(args.get("action", "")).lower()
        items = args.get("items", [])
        if not isinstance(items, list):
            continue

        if action == "add":
            next_note_number += await _add_items(
                entries,
                items,
                ctx,
                next_note_number,
                before_step_order=getattr(step, "step_order", None),
            )
        elif action == "remove":
            _remove_items(entries, items)

    return entries, next_note_number


def format_notebook_output(entries: list[NotebookEntry]) -> str:
    if not entries:
        return NOTEBOOK_EMPTY_OUTPUT

    lines = ["<notebook>", ""]
    for entry in entries:
        lines.append(f'<note id="{escape(entry.id)}" type="{escape(entry.type)}">')
        if entry.type == "text":
            if entry.text:
                lines.append(escape(entry.text))
        else:
            meta = _format_attrs(entry.attrs)
            if meta:
                lines.append(meta)
            if entry.body:
                lines.append(escape(entry.body))
            if entry.text:
                if entry.body or meta:
                    lines.append("---")
                    lines.append(f"[annotation] {escape(entry.text)}")
                else:
                    lines.append(escape(entry.text))
        lines.append("</note>")
        lines.append("")
    lines.append("</notebook>")
    return "\n".join(lines)


async def _load_notebook_steps(
    ctx: ToolContext,
    *,
    before_step_order: int | None = None,
) -> list[Any]:
    stmt = (
        select(ConversationStep)
        .where(
            ConversationStep.conversation_id == ctx.conversation_id,
            ConversationStep.step_type == "tool_call",
        )
        .order_by(ConversationStep.step_order.asc())
    )
    if before_step_order is not None:
        stmt = stmt.where(ConversationStep.step_order < before_step_order)

    result = await ctx.db.execute(stmt)
    steps = list(result.scalars().all())
    return [
        step
        for step in steps
        if getattr(step, "conversation_id", ctx.conversation_id) == ctx.conversation_id
        and getattr(step, "step_type", "tool_call") == "tool_call"
        and (
            getattr(step, "tool_type", None) == "notebook"
            or getattr(step, "tool_name", None) == "notebook"
        )
        and (
            before_step_order is None
            or getattr(step, "step_order", before_step_order) < before_step_order
        )
    ]


async def _add_items(
    entries: list[NotebookEntry],
    items: list[dict],
    ctx: ToolContext,
    next_note_number: int,
    *,
    before_step_order: int | None = None,
) -> int:
    added = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = await _build_entry(
            f"note_{next_note_number:03d}",
            item,
            ctx,
            before_step_order=before_step_order,
        )
        if entry is None:
            continue
        entries.append(entry)
        next_note_number += 1
        added += 1
    return added


def _remove_items(entries: list[NotebookEntry], items: list[dict]) -> int:
    ids = {
        str(item.get("id", "")).strip()
        for item in items
        if isinstance(item, dict)
    }
    ids.discard("")
    if not ids:
        return 0

    before = len(entries)
    entries[:] = [entry for entry in entries if entry.id not in ids]
    return before - len(entries)


async def _build_entry(
    note_id: str,
    item: dict,
    ctx: ToolContext,
    *,
    before_step_order: int | None,
) -> NotebookEntry | None:
    slice_id = _clean_id(item.get("slice_id"))
    doc_id = _clean_id(item.get("doc_id"))
    line = _clean_id(item.get("line"))
    text = _clean_text(item.get("text"))

    if not slice_id and not doc_id and not line and not text:
        return None

    if slice_id:
        resolved = await _resolve_slice_entry(
            ctx,
            slice_id=slice_id,
            doc_id=doc_id,
            before_step_order=before_step_order,
        )
        attrs = resolved.attrs if resolved else {"slice_id": slice_id}
        if doc_id and "doc_id" not in attrs:
            attrs["doc_id"] = doc_id
        return NotebookEntry(
            id=note_id,
            type="slice",
            attrs=attrs,
            body=resolved.body if resolved else None,
            text=text,
        )

    if doc_id and line:
        resolved = await _resolve_grep_match_entry(
            ctx,
            doc_id=doc_id,
            line=line,
            before_step_order=before_step_order,
        )
        return NotebookEntry(
            id=note_id,
            type="grep_match",
            attrs=resolved.attrs if resolved else {"doc_id": doc_id, "line": line},
            body=resolved.body if resolved else None,
            text=text,
        )

    if doc_id:
        resolved = await _resolve_doc_entry(
            ctx,
            doc_id=doc_id,
            before_step_order=before_step_order,
        )
        return NotebookEntry(
            id=note_id,
            type="doc",
            attrs=resolved.attrs if resolved else {"doc_id": doc_id},
            body=resolved.body if resolved else None,
            text=text,
        )

    return NotebookEntry(id=note_id, type="text", text=text)


@dataclass
class _ResolvedToolEntry:
    attrs: dict[str, str]
    body: str | None = None


async def _resolve_slice_entry(
    ctx: ToolContext,
    *,
    slice_id: str,
    doc_id: str | None,
    before_step_order: int | None,
) -> _ResolvedToolEntry | None:
    from_tool_response = await _find_prior_tool_entry(
        ctx,
        tool_type="search",
        tag_name="result",
        id_field="slice_id",
        id_value=slice_id,
        before_step_order=before_step_order,
    )
    if from_tool_response:
        return from_tool_response

    parsed_slice_id = _parse_int(slice_id)
    if parsed_slice_id is None:
        return None

    result = await ctx.db.execute(
        select(Slice)
        .where(Slice.id == parsed_slice_id, Slice.tenant_id == ctx.tenant_id)
        .limit(1)
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None

    attrs = {
        "slice_id": str(item.id),
        "doc_id": str(item.document_id),
    }
    if item.toc_path:
        attrs["toc_path"] = " > ".join(str(v) for v in item.toc_path)
    return _ResolvedToolEntry(attrs=attrs, body=item.content)


async def _resolve_doc_entry(
    ctx: ToolContext,
    *,
    doc_id: str,
    before_step_order: int | None,
) -> _ResolvedToolEntry | None:
    from_tool_response = await _find_prior_tool_entry(
        ctx,
        tool_type="doc_query",
        tag_name="doc",
        id_field="doc_id",
        id_value=doc_id,
        before_step_order=before_step_order,
    )
    if from_tool_response:
        return from_tool_response

    parsed_doc_id = _parse_int(doc_id)
    if parsed_doc_id is None:
        return None

    result = await ctx.db.execute(
        select(Document)
        .where(Document.id == parsed_doc_id, Document.tenant_id == ctx.tenant_id)
        .limit(1)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        return None

    attrs = {"doc_id": str(doc.id)}
    if doc.title:
        attrs["title"] = doc.title
    if doc.description:
        attrs["description"] = doc.description
    return _ResolvedToolEntry(attrs=attrs)


async def _resolve_grep_match_entry(
    ctx: ToolContext,
    *,
    doc_id: str,
    line: str,
    before_step_order: int | None,
) -> _ResolvedToolEntry | None:
    stmt = (
        select(ConversationStep)
        .where(
            ConversationStep.conversation_id == ctx.conversation_id,
            ConversationStep.step_type == "tool_call",
            ConversationStep.tool_type == "doc_grep",
        )
        .order_by(ConversationStep.step_order.desc())
    )
    if before_step_order is not None:
        stmt = stmt.where(ConversationStep.step_order < before_step_order)

    result = await ctx.db.execute(stmt)
    steps = list(result.scalars().all())
    for step in sorted(steps, key=lambda s: getattr(s, "step_order", 0), reverse=True):
        if getattr(step, "tool_type", None) != "doc_grep":
            continue
        if (
            before_step_order is not None
            and getattr(step, "step_order", 0) >= before_step_order
        ):
            continue
        parsed = _extract_grep_match_from_xml(
            step.tool_response or "",
            doc_id=doc_id,
            line=line,
        )
        if parsed:
            return parsed
    return None


async def _find_prior_tool_entry(
    ctx: ToolContext,
    *,
    tool_type: str,
    tag_name: str,
    id_field: str,
    id_value: str,
    before_step_order: int | None,
) -> _ResolvedToolEntry | None:
    stmt = (
        select(ConversationStep)
        .where(
            ConversationStep.conversation_id == ctx.conversation_id,
            ConversationStep.step_type == "tool_call",
            ConversationStep.tool_type == tool_type,
        )
        .order_by(ConversationStep.step_order.desc())
    )
    if before_step_order is not None:
        stmt = stmt.where(ConversationStep.step_order < before_step_order)

    result = await ctx.db.execute(stmt)
    steps = list(result.scalars().all())
    for step in sorted(steps, key=lambda s: getattr(s, "step_order", 0), reverse=True):
        if getattr(step, "tool_type", None) != tool_type:
            continue
        if before_step_order is not None and getattr(step, "step_order", 0) >= before_step_order:
            continue
        parsed = _extract_tool_entry_from_xml(
            step.tool_response or "",
            tag_name=tag_name,
            id_field=id_field,
            id_value=id_value,
        )
        if parsed:
            return parsed
    return None


def _extract_tool_entry_from_xml(
    raw_xml: str,
    *,
    tag_name: str,
    id_field: str,
    id_value: str,
) -> _ResolvedToolEntry | None:
    if not raw_xml:
        return None
    try:
        root = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        return None

    for elem in root.iter(tag_name):
        attrs = {str(k): str(v) for k, v in elem.attrib.items()}
        if attrs.get(id_field) != id_value:
            continue
        body = (elem.text or "").strip()
        return _ResolvedToolEntry(attrs=attrs, body=body or None)
    return None


def _extract_grep_match_from_xml(
    raw_xml: str,
    *,
    doc_id: str,
    line: str,
) -> _ResolvedToolEntry | None:
    if not raw_xml:
        return None
    try:
        root = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        return None

    root_attrs = {str(k): str(v) for k, v in root.attrib.items()}
    if root_attrs.get("doc_id") and root_attrs["doc_id"] != doc_id:
        return None

    for elem in root.iter("match"):
        match_attrs = {str(k): str(v) for k, v in elem.attrib.items()}
        if match_attrs.get("line") != line:
            continue

        attrs = {"doc_id": root_attrs.get("doc_id", doc_id), "line": line}
        if root_attrs.get("pattern"):
            attrs["pattern"] = root_attrs["pattern"]
        for key, value in match_attrs.items():
            if key != "line":
                attrs[key] = value

        body = "".join(elem.itertext()).strip()
        return _ResolvedToolEntry(attrs=attrs, body=body or None)
    return None


def _response(action: str, message: str, total: int) -> str:
    return (
        f'<notebook_response action="{action}">\n'
        f"{escape(message)} Current total: {total} items.\n"
        f"</notebook_response>"
    )


def _format_attrs(attrs: dict[str, str]) -> str:
    ordered_keys = [
        key for key in ("slice_id", "doc_id") if key in attrs
    ] + [key for key in attrs if key not in {"slice_id", "doc_id"}]
    parts = [
        f'{key}="{escape(str(value))}"'
        for key in ordered_keys
        for value in [attrs[key]]
        if value is not None and str(value) != ""
    ]
    return " ".join(parts)


def _clean_id(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
