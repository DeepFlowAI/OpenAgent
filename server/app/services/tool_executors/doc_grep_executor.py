"""
Doc grep tool executor — searches within a single document's readable Markdown.
Response format: XML <grep_results> per design spec.
"""
import re
from dataclasses import dataclass
from xml.sax.saxutils import escape

from sqlalchemy import select

from app.libs.doc_parser.parser import clean_markdown_for_reading
from app.models.document import Document
from app.services.tool_executors.base import BaseToolExecutor, ToolContext

MAX_MATCHES = 20
MAX_PATTERN_LENGTH = 200
DEFAULT_CONTEXT_LINES = 5
MAX_CONTEXT_LINES = 100


@dataclass(frozen=True)
class _MatchWindow:
    line: int
    start: int
    end: int


class DocGrepToolExecutor(BaseToolExecutor):
    """Search a known document by Python regex and return line-level context."""

    async def execute(self, args: dict, config: dict, ctx: ToolContext) -> str:
        del config

        doc_id, doc_id_error = _parse_doc_id(args.get("doc_id"))
        if doc_id_error:
            return _error(doc_id_error)

        pattern = str(args.get("pattern") or "")
        if not pattern:
            return _error("pattern is required.")
        if len(pattern) > MAX_PATTERN_LENGTH:
            return _error(
                f"Pattern too long (len={len(pattern)}, max={MAX_PATTERN_LENGTH}). "
                "Please use a shorter pattern."
            )

        context_lines, context_error = _parse_context_lines(args.get("context_lines"))
        if context_error:
            return _error(context_error)

        ignore_case = args.get("ignore_case", True)
        flags = re.IGNORECASE if bool(ignore_case) else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as exc:
            return _error(f"Invalid pattern — re.error: {exc}. Please fix the regex and retry.")

        doc = await _get_document(ctx, doc_id)
        if doc is None:
            return _error(f"Document not found (doc_id={doc_id}).")

        readable = clean_markdown_for_reading(doc.markdown_content or "")
        lines = readable.splitlines()
        match_lines, total_matches = _collect_matches(lines, regex)
        return _format_results(doc_id, pattern, lines, match_lines, total_matches, context_lines)


async def _get_document(ctx: ToolContext, doc_id: int) -> Document | None:
    """Load a document from the current tenant, without knowledge-base restriction."""
    result = await ctx.db.execute(
        select(Document).where(
            Document.id == doc_id,
            Document.tenant_id == ctx.tenant_id,
        )
    )
    return result.scalar_one_or_none()


def _parse_doc_id(raw_doc_id: object) -> tuple[int, str | None]:
    if raw_doc_id is None or raw_doc_id == "":
        return 0, "doc_id is required."
    try:
        return int(str(raw_doc_id)), None
    except (TypeError, ValueError):
        return 0, f"Invalid doc_id ({raw_doc_id})."


def _parse_context_lines(raw_context_lines: object) -> tuple[int, str | None]:
    if raw_context_lines is None:
        return DEFAULT_CONTEXT_LINES, None
    try:
        value = int(raw_context_lines)
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_LINES, f"context_lines must be an integer between 0 and {MAX_CONTEXT_LINES}."
    if value < 0 or value > MAX_CONTEXT_LINES:
        return DEFAULT_CONTEXT_LINES, f"context_lines must be between 0 and {MAX_CONTEXT_LINES}."
    return value, None


def _collect_matches(lines: list[str], regex: re.Pattern[str]) -> tuple[list[int], int]:
    match_lines: list[int] = []
    total_matches = 0
    for index, line in enumerate(lines, start=1):
        if regex.search(line):
            total_matches += 1
            if len(match_lines) < MAX_MATCHES:
                match_lines.append(index)
    return match_lines, total_matches


def _format_results(
    doc_id: int,
    pattern: str,
    lines: list[str],
    match_lines: list[int],
    total_matches: int,
    context_lines: int,
) -> str:
    showing = len(match_lines)
    attrs = (
        f'doc_id="{_attr(doc_id)}" '
        f'pattern="{_attr(pattern)}" '
        f'total_matches="{total_matches}" '
        f'showing="{showing}"'
    )
    if not match_lines:
        return f"<grep_results {attrs}>\n</grep_results>"

    windows = _merge_windows(match_lines, len(lines), context_lines)
    output = [f"<grep_results {attrs}>", ""]
    for window in windows:
        output.append(f'<match line="{window.line}">')
        for line_no in range(window.start, window.end + 1):
            output.append(f"{line_no}| {escape(lines[line_no - 1])}")
        output.append("</match>")
        output.append("")
    output.append("</grep_results>")
    return "\n".join(output)


def _merge_windows(match_lines: list[int], line_count: int, context_lines: int) -> list[_MatchWindow]:
    windows: list[_MatchWindow] = []
    for line in match_lines:
        start = max(1, line - context_lines)
        end = min(line_count, line + context_lines)
        if windows and start <= windows[-1].end + 1:
            previous = windows[-1]
            windows[-1] = _MatchWindow(
                line=previous.line,
                start=previous.start,
                end=max(previous.end, end),
            )
            continue
        windows.append(_MatchWindow(line=line, start=start, end=end))
    return windows


def _error(message: str) -> str:
    return f"<grep_results>\nError: {escape(message)}\n</grep_results>"


def _attr(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})
