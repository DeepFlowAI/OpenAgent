"""
Order KB documents using schema/nav.yaml semantics.

Mirrors `web/app/(visitor)/hc/[slug]/_components/doc-tree-utils.ts`:
nav-declared siblings first (per parent), then unlisted items: folders before
files, then display-name comparison (best-effort locale when available).
"""
from __future__ import annotations

import locale
from dataclasses import dataclass, field
from functools import cmp_to_key
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class _DocumentLike(Protocol):
    file_path: str
    title: str | None


@dataclass
class _TreeFile:
    kind: str = "file"
    name: str = ""
    file_path: str = ""
    title: str | None = None
    doc: Any = None


@dataclass
class _TreeFolder:
    kind: str = "folder"
    name: str = ""
    path: list[str] = field(default_factory=list)
    children: list[Any] = field(default_factory=list)


def _build_nav_order_maps(
    nav: list | None,
) -> tuple[dict[str, int], dict[str, int]]:
    file_order: dict[str, int] = {}
    folder_order: dict[str, int] = {}

    if not nav:
        return file_order, folder_order

    def walk(entries: list, path_prefix: str) -> None:
        position = 0
        for entry in entries:
            if isinstance(entry, str):
                full_path = (
                    f"{path_prefix}/{entry}" if path_prefix else entry
                )
                file_order[full_path] = position
                position += 1
                continue
            if isinstance(entry, dict) and "file" in entry:
                fn = entry.get("file")
                if not isinstance(fn, str):
                    continue
                full_path = f"{path_prefix}/{fn}" if path_prefix else fn
                file_order[full_path] = position
                position += 1
                continue
            if isinstance(entry, dict) and "folder" in entry:
                fd = entry.get("folder")
                if not isinstance(fd, str):
                    continue
                folder_path = f"{path_prefix}/{fd}" if path_prefix else fd
                folder_order[folder_path] = position
                position += 1
                children = entry.get("children")
                if isinstance(children, list):
                    walk(children, folder_path)

    walk(nav, "")
    return file_order, folder_order


def _node_key(node: _TreeFile | _TreeFolder) -> str:
    if node.kind == "file":
        return node.file_path
    return "/".join(node.path)


def _lookup_order(
    node: _TreeFile | _TreeFolder,
    key: str,
    file_order: dict[str, int],
    folder_order: dict[str, int],
) -> int | None:
    if node.kind == "file":
        return file_order.get(key)
    return folder_order.get(key)


def _display_name(node: _TreeFile | _TreeFolder) -> str:
    if node.kind == "file":
        return (node.title or node.name or "").strip()
    return (node.name or "").strip()


def _cmp_display(a: str, b: str) -> int:
    aa = a or ""
    bb = b or ""
    try:
        c = locale.strcoll(aa, bb)
    except Exception:
        return (aa > bb) - (aa < bb)
    return (c > 0) - (c < 0)


def _sort_children(
    node: _TreeFolder,
    file_order: dict[str, int],
    folder_order: dict[str, int],
) -> None:
    def cmp(a: Any, b: Any) -> int:
        a_key = _node_key(a)
        b_key = _node_key(b)
        a_ord = _lookup_order(a, a_key, file_order, folder_order)
        b_ord = _lookup_order(b, b_key, file_order, folder_order)
        a_has = a_ord is not None
        b_has = b_ord is not None
        if a_has and b_has:
            assert a_ord is not None and b_ord is not None
            return (a_ord > b_ord) - (a_ord < b_ord)
        if a_has and not b_has:
            return -1
        if not a_has and b_has:
            return 1
        if a.kind != b.kind:
            return -1 if a.kind == "folder" else 1
        name_cmp = _cmp_display(_display_name(a), _display_name(b))
        if name_cmp != 0:
            return name_cmp
        tie_a = a.file_path if a.kind == "file" else "/".join(a.path)
        tie_b = b.file_path if b.kind == "file" else "/".join(b.path)
        return _cmp_display(tie_a, tie_b)

    node.children.sort(key=cmp_to_key(cmp))

    for ch in node.children:
        if ch.kind == "folder":
            _sort_children(ch, file_order, folder_order)


def _insert_doc(root: _TreeFolder, doc: _DocumentLike) -> None:
    segments = [s for s in doc.file_path.split("/") if s]
    if not segments:
        return
    file_name = segments[-1]
    folder_segs = segments[:-1]
    cursor = root
    for i, seg in enumerate(folder_segs):
        cumulative = folder_segs[: i + 1]
        nxt = None
        for c in cursor.children:
            if c.kind == "folder" and c.name == seg:
                nxt = c
                break
        if nxt is None:
            nxt = _TreeFolder(name=seg, path=cumulative, children=[])
            cursor.children.append(nxt)
        cursor = nxt
    cursor.children.append(
        _TreeFile(
            name=file_name,
            file_path=doc.file_path,
            title=doc.title,
            doc=doc,
        )
    )


def _flatten_files(node: _TreeFolder) -> list[Any]:
    out: list[Any] = []
    for ch in node.children:
        if ch.kind == "file":
            out.append(ch.doc)
        else:
            out.extend(_flatten_files(ch))
    return out


def sort_documents_by_kb_nav(
    documents: list[_DocumentLike],
    nav: list | None,
) -> list[_DocumentLike]:
    """
    Return documents in help-center sidebar order (DFS), using `nav` when
    provided (including an empty list: nav maps empty → fallback only).
    """
    root = _TreeFolder(name="", path=[], children=[])
    for d in documents:
        _insert_doc(root, d)
    file_order, folder_order = _build_nav_order_maps(nav)
    _sort_children(root, file_order, folder_order)
    return _flatten_files(root)
