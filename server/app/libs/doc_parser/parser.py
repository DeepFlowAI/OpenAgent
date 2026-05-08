"""
Programmable Document Parser

Implements the parsing pipeline defined in 《可编程文档规范》:
1. Read YAML Frontmatter → doc-meta
2. Split body by +++ → slices
3. Parse <slice-meta> blocks in each slice
4. Build TOC from headings, attach toc_path to slices
5. Resolve content_template placeholders → content_for_search
"""
import os
import re
import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Only horizontal spaces after +++; do not use \s* here — in CRLF files \s would match
# \r/\n and incorrectly consume the following blank line (or part of the next heading line),
# shifting segment boundaries and breaking toc_path when first-heading detection fails.
SLICE_SEPARATOR_RE = re.compile(r"^[ \t]*\+\+\+[ \t]*\r?$", re.MULTILINE)
SLICE_META_RE = re.compile(
    r"<slice-meta>\s*\n(.*?)\n\s*</slice-meta>", re.DOTALL
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
FENCED_YAML_RE = re.compile(
    r"```(?:yaml(?:\s+slice-meta)?)\s*\n(.*?)\n```", re.DOTALL
)

PLACEHOLDER_BASIC_RE = re.compile(r"\{(doc|slice)\.(\w+)\}")
PLACEHOLDER_LABEL_RE = re.compile(r"\{([^'{}]*)'(doc|slice)\.(\w+)'\}")
PLACEHOLDER_SPECIAL = re.compile(r"\{(toc_path|toc_ancestors|body)\}")


class ParsedDocument:
    def __init__(self):
        self.file_path: str = ""
        self.title: str | None = None
        self.description: str | None = None
        self.source_url: str | None = None
        self.doc_meta: dict[str, Any] = {}
        self.vector_config: dict[str, Any] = {}
        self.toc: list[dict] = []
        self.markdown_content: str = ""
        self.slices: list["ParsedSlice"] = []


class ParsedSlice:
    def __init__(self):
        self.content: str = ""
        self.content_for_search: str = ""
        self.toc_path: list[str] = []
        # Precomputed for content_template / embeddings (do not re-join from toc_path in _apply_template)
        self.toc_path_joined: str = ""
        # Ancestor heading path only (toc_path without last segment); None when depth <= 1
        self.toc_ancestors: str | None = None
        self.slice_meta: dict[str, Any] = {}
        self.slice_order: int = 0


def parse_document(
    file_path: str,
    content: str,
    *,
    doc_field_types: dict[str, str] | None = None,
    slice_field_types: dict[str, str] | None = None,
) -> ParsedDocument:
    """Parse a single programmable markdown document.

    ``doc_field_types`` / ``slice_field_types`` are optional ``{field_name: semantic_type}``
    maps derived from ``schema/doc-meta.yaml`` / ``schema/slice-meta.yaml``. When provided,
    the parser normalizes array-typed values (``keyword[]`` / ``integer[]``) per spec
    §4.2.1: YAML lists are kept, single scalars are wrapped into single-element arrays,
    and empty-ish values are dropped.
    """
    doc = ParsedDocument()
    doc.file_path = file_path
    doc.markdown_content = content

    body = _parse_frontmatter(content, doc)
    if doc_field_types:
        doc.doc_meta = _normalize_meta_by_schema(doc.doc_meta, doc_field_types)
    _build_toc(body, doc)
    _split_and_parse_slices(body, doc)
    if slice_field_types:
        for s in doc.slices:
            s.slice_meta = _normalize_meta_by_schema(s.slice_meta, slice_field_types)
    _resolve_templates(doc)

    return doc


def _parse_frontmatter(content: str, doc: ParsedDocument) -> str:
    """Extract YAML frontmatter, populate doc.doc_meta. Returns body after frontmatter."""
    match = FRONTMATTER_RE.match(content)
    if not match:
        return content

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        logger.warning("Frontmatter parse error in %s: %s", doc.file_path, exc)
        return content[match.end():]

    meta = _sanitize_meta(meta)
    doc.doc_meta = {k: v for k, v in meta.items() if k != "vector"}
    doc.title = meta.get("title")
    doc.description = meta.get("description")
    doc.source_url = meta.get("source")
    doc.vector_config = meta.get("vector", {})

    return content[match.end():]


def _sanitize_meta(obj: Any) -> Any:
    """Convert non-JSON-serializable types (date, datetime) to strings recursively."""
    import datetime as dt

    if isinstance(obj, dict):
        return {k: _sanitize_meta(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_meta(v) for v in obj]
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    return obj


# Semantic types that must be persisted as JSON arrays for `has_any`/`has_all`
# filtering to work. Keep this set small and aligned with §4.2 of the spec.
_ARRAY_SEMANTIC_TYPES: frozenset[str] = frozenset({"keyword[]", "integer[]"})


def _coerce_array_value(field_name: str, raw: Any, semantic_type: str) -> Any:
    """Normalize a raw YAML value to a JSON array per spec §4.2.1.

    Returns the normalized array, or ``None`` to signal "drop this field".

    - list ``[a, b]`` → kept (each element coerced to target element type)
    - scalar ``foo`` → ``[foo]`` (single-token shortcut)
    - ``None``/``""``/``[]`` → ``None`` (treated as unset; not stored)
    - dict / unsupported → ``None`` + warning (avoid silently mis-shaping data)
    """
    if raw is None:
        return None
    if isinstance(raw, str) and raw == "":
        return None
    if isinstance(raw, list):
        if len(raw) == 0:
            return None
        items = raw
    elif isinstance(raw, (str, int, float, bool)):
        items = [raw]
    else:
        logger.warning(
            "Field %r declared as %s but got unsupported value type %s; dropping",
            field_name, semantic_type, type(raw).__name__,
        )
        return None

    if semantic_type == "keyword[]":
        return [str(x) for x in items if x is not None and x != ""]
    if semantic_type == "integer[]":
        coerced: list[int] = []
        for x in items:
            try:
                coerced.append(int(x))
            except (TypeError, ValueError):
                logger.warning(
                    "Field %r declared as integer[] but element %r is not int-coercible; dropping element",
                    field_name, x,
                )
        return coerced or None

    return items


def _normalize_meta_by_schema(
    meta: dict[str, Any], field_types: dict[str, str]
) -> dict[str, Any]:
    """Apply schema-driven normalization to a parsed meta dict.

    Only array-typed fields are touched (per spec §4.2.1). Other fields stay
    as-is so unknown / future types are not silently coerced.
    """
    if not meta or not field_types:
        return meta

    out = dict(meta)
    for name, semantic_type in field_types.items():
        if semantic_type not in _ARRAY_SEMANTIC_TYPES:
            continue
        if name not in out:
            continue
        normalized = _coerce_array_value(name, out[name], semantic_type)
        if normalized is None:
            out.pop(name, None)
        else:
            out[name] = normalized
    return out


def _build_toc(body: str, doc: ParsedDocument) -> None:
    """Build TOC tree from headings."""
    toc: list[dict] = []
    for match in HEADING_RE.finditer(body):
        level = len(match.group(1))
        text = match.group(2).strip()
        toc.append({"level": level, "text": text, "pos": match.start()})
    doc.toc = toc


def _get_toc_path_at(pos: int, toc: list[dict]) -> list[str]:
    """Compute toc_path stack at a given position."""
    stack: list[tuple[int, str]] = []
    for entry in toc:
        if entry["pos"] > pos:
            break
        level = entry["level"]
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, entry["text"]))
    return [s[1] for s in stack]


def toc_ancestors_for_storage(toc_path: list[str] | None) -> str | None:
    """Value persisted on Slice; same semantics as {toc_ancestors} in content_template."""
    if not toc_path or len(toc_path) <= 1:
        return None
    return " > ".join(toc_path[:-1])


def _iter_slice_segments(body: str):
    """Yield (start_index_in_body, segment_text) for each region between +++ lines.

    re.split drops separators and a fixed "+3" skip is wrong (separators are full lines,
    often \\n+++\\n). Using match spans keeps heading positions aligned with doc.toc.
    """
    start = 0
    for m in SLICE_SEPARATOR_RE.finditer(body):
        yield start, body[start : m.start()]
        start = m.end()
    yield start, body[start:]


def _split_and_parse_slices(body: str, doc: ParsedDocument) -> None:
    """Split body by +++ and parse each slice."""
    slice_order = 0
    for current_pos, part in _iter_slice_segments(body):
        part_stripped = part.strip()
        if not part_stripped:
            continue

        s = ParsedSlice()
        s.slice_order = slice_order
        slice_order += 1

        toc_path = _get_toc_path_at(current_pos, doc.toc)

        headings_in_part = list(HEADING_RE.finditer(part))
        if headings_in_part:
            first_heading_offset = current_pos + headings_in_part[0].start()
            toc_path = _get_toc_path_at(first_heading_offset + 1, doc.toc)

        s.toc_path = toc_path
        s.toc_path_joined = " > ".join(toc_path) if toc_path else ""
        s.toc_ancestors = toc_ancestors_for_storage(toc_path)

        slice_body, slice_meta = _extract_slice_meta(part_stripped)
        s.content = slice_body
        s.slice_meta = _flatten_fields_meta(slice_meta)

        if s.slice_meta.get("vector"):
            s.slice_meta = {k: v for k, v in s.slice_meta.items() if k != "vector"}

        doc.slices.append(s)


def _flatten_fields_meta(meta: dict) -> dict:
    """Flatten nested {meta, fields} format to flat {field_name: value} dict.

    Input:  {"meta": {...}, "fields": [{"name": "power_w", "value": 0.11}, ...]}
    Output: {"power_w": 0.11, ...}

    If meta has no "fields" key (already flat), returns as-is.
    """
    if not meta or "fields" not in meta:
        return meta

    fields = meta.get("fields", [])
    if not isinstance(fields, list):
        return meta

    flat: dict = {}
    for k, v in meta.items():
        if k not in ("meta", "fields"):
            flat[k] = v

    for field in fields:
        if isinstance(field, dict) and "name" in field and "value" in field:
            flat[field["name"]] = field["value"]

    return flat


def _extract_slice_meta(text: str) -> tuple[str, dict]:
    """Extract <slice-meta> block from slice text. Returns (body_without_meta, meta_dict)."""
    match = SLICE_META_RE.search(text)
    if not match:
        return text, {}

    meta_raw = match.group(1)

    fenced = FENCED_YAML_RE.search(meta_raw)
    yaml_str = fenced.group(1) if fenced else meta_raw

    try:
        meta = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError as exc:
        logger.warning("slice-meta parse error: %s", exc)
        meta = {}

    meta = _sanitize_meta(meta)
    body = text[:match.start()] + text[match.end():]
    return body.strip(), meta


def _resolve_templates(doc: ParsedDocument) -> None:
    """Resolve content_template placeholders for each slice."""
    template = doc.vector_config.get("content_template", "{body}")

    for s in doc.slices:
        slice_template = s.slice_meta.get("vector", {}).get(
            "content_template", template
        )
        s.content_for_search = _apply_template(
            slice_template, doc, s
        )


def _apply_template(template: str, doc: ParsedDocument, s: ParsedSlice) -> str:
    """Apply placeholder resolution to a template string."""
    result = template

    def replace_basic(m: re.Match) -> str:
        ns, field = m.group(1), m.group(2)
        source = doc.doc_meta if ns == "doc" else s.slice_meta
        val = source.get(field)
        return str(val) if val is not None else ""

    def replace_label(m: re.Match) -> str:
        label, ns, field = m.group(1), m.group(2), m.group(3)
        source = doc.doc_meta if ns == "doc" else s.slice_meta
        val = source.get(field)
        if val is None or val == "":
            return ""
        return f"{label}{val}"

    def replace_special(m: re.Match) -> str:
        name = m.group(1)
        if name == "body":
            return s.content
        if name == "toc_path":
            return s.toc_path_joined
        if name == "toc_ancestors":
            # Parse-time field only; never derive from s.toc_path here (same value as persisted Slice.toc_ancestors).
            return s.toc_ancestors or ""
        return ""

    result = PLACEHOLDER_LABEL_RE.sub(replace_label, result)
    result = PLACEHOLDER_BASIC_RE.sub(replace_basic, result)
    result = PLACEHOLDER_SPECIAL.sub(replace_special, result)

    return result.strip()


def clean_markdown_for_reading(content: str) -> str:
    """Strip frontmatter, slice-meta blocks, and +++ separators to produce
    a human-readable markdown string."""
    text = FRONTMATTER_RE.sub("", content)
    text = SLICE_META_RE.sub("", text)
    text = SLICE_SEPARATOR_RE.sub("", text)
    return text.strip()


def discover_markdown_files(repo_dir: str) -> list[str]:
    """Find all .md files outside schema/ directory. Returns relative paths."""
    md_files: list[str] = []
    schema_dir = os.path.join(repo_dir, "schema")

    for root, _dirs, files in os.walk(repo_dir):
        if root == schema_dir or root.startswith(schema_dir + os.sep):
            continue
        if os.path.basename(root) == ".git":
            continue
        if ".git" in root.split(os.sep):
            continue
        for f in files:
            if f.endswith(".md"):
                full = os.path.join(root, f)
                rel = os.path.relpath(full, repo_dir)
                md_files.append(rel)

    return sorted(md_files)
