"""Unit tests for KB document ordering by schema/nav.yaml (help-center parity)."""
from dataclasses import dataclass

from app.libs.doc_parser.kb_nav_doc_order import sort_documents_by_kb_nav


@dataclass
class _MiniDoc:
    file_path: str
    title: str | None = None


def test_nav_root_file_order_before_unlisted():
    nav = [
        "README.md",
        {"folder": "a", "children": [{"file": "x.md"}]},
    ]
    docs = [
        _MiniDoc("b-extra.md"),
        _MiniDoc("a/x.md"),
        _MiniDoc("README.md"),
    ]
    out = sort_documents_by_kb_nav(docs, nav)
    assert [d.file_path for d in out] == ["README.md", "a/x.md", "b-extra.md"]


def test_fallback_folders_before_files_when_not_in_nav():
    nav: list | None = []
    docs = [
        _MiniDoc("z/f.md"),
        _MiniDoc("readme.md"),
    ]
    out = sort_documents_by_kb_nav(docs, nav)
    # Unlisted siblings: folder "z" before file "readme.md"
    assert [d.file_path for d in out] == ["z/f.md", "readme.md"]


def test_string_and_dict_file_entries_equivalent():
    nav = ["a.md", {"file": "b.md"}]
    docs = [_MiniDoc("b.md"), _MiniDoc("a.md")]
    out = sort_documents_by_kb_nav(docs, nav)
    assert [d.file_path for d in out] == ["a.md", "b.md"]


def test_fallback_tie_breaks_by_file_path_when_display_names_equal():
    nav: list | None = []
    docs = [
        _MiniDoc("a/b.md", title="Same"),
        _MiniDoc("a/z.md", title="Same"),
    ]
    out = sort_documents_by_kb_nav(docs, nav)
    assert [d.file_path for d in out] == ["a/b.md", "a/z.md"]
