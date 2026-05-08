"""
Unit tests for the programmable document parser
"""
import pytest

from app.libs.doc_parser.parser import parse_document, discover_markdown_files


class TestParseDocument:

    def test_parse_frontmatter_extracts_doc_meta(self):
        content = """---
title: Test Document
description: A test
tags: [prd, test]
author: Zhang San
created: 2025-03-01
---
# Hello World

Some content here.
"""
        doc = parse_document("test.md", content)
        assert doc.title == "Test Document"
        assert doc.description == "A test"
        assert doc.doc_meta["tags"] == ["prd", "test"]
        assert doc.doc_meta["author"] == "Zhang San"
        assert doc.file_path == "test.md"

    def test_parse_no_frontmatter(self):
        content = "# Just a heading\n\nSome text."
        doc = parse_document("no-fm.md", content)
        assert doc.title is None
        assert doc.doc_meta == {}
        assert len(doc.slices) == 1

    def test_split_slices_by_separator(self):
        content = """---
title: Multi-slice
---
## Section A
Content A
+++
## Section B
Content B
+++
## Section C
Content C
"""
        doc = parse_document("multi.md", content)
        assert len(doc.slices) == 3
        assert "Content A" in doc.slices[0].content
        assert "Content B" in doc.slices[1].content
        assert "Content C" in doc.slices[2].content

    def test_slice_separator_crlf_does_not_shift_toc_path(self):
        """CRLF + old \\s*-based +++ regex could swallow extra newlines; toc_path must stay correct."""
        content = (
            "---\ntitle: CRLF\n---\n"
            "## 《Product A》\n"
            "A\n"
            "<slice-meta>\n```yaml slice-meta\nx: 1\n```\n</slice-meta>\r\n"
            "+++\r\n"
            "\r\n"
            "## 《Product B》\n"
            "B\n"
            "<slice-meta>\n```yaml slice-meta\nx: 2\n```\n</slice-meta>\r\n"
            "+++\r\n"
            "\r\n"
            "## 《Product C》\n"
            "C\n"
        )
        doc = parse_document("crlf.md", content)
        assert len(doc.slices) == 3
        assert doc.slices[0].toc_path == ["《Product A》"]
        assert doc.slices[1].toc_path == ["《Product B》"]
        assert doc.slices[2].toc_path == ["《Product C》"]

    def test_single_slice_when_no_separator(self):
        content = """---
title: Single
---
Just one big document.
"""
        doc = parse_document("single.md", content)
        assert len(doc.slices) == 1
        assert "Just one big document" in doc.slices[0].content

    def test_toc_path_assigned_to_slices(self):
        content = """---
title: TOC Test
---
## Chapter 1
+++
### Background
Background content
+++
## Chapter 2
+++
### Background
Another background
"""
        doc = parse_document("toc.md", content)
        assert doc.slices[0].toc_path == ["Chapter 1"]
        assert doc.slices[0].toc_ancestors is None
        assert doc.slices[1].toc_path == ["Chapter 1", "Background"]
        assert doc.slices[1].toc_ancestors == "Chapter 1"
        assert doc.slices[2].toc_path == ["Chapter 2"]
        assert doc.slices[2].toc_ancestors is None
        assert doc.slices[3].toc_path == ["Chapter 2", "Background"]
        assert doc.slices[3].toc_ancestors == "Chapter 2"

    def test_slice_meta_extraction(self):
        content = """---
title: Slice Meta Test
---
+++

<slice-meta>
```yaml slice-meta
question: How to reset password?
category: Account Security
```
</slice-meta>

Users can reset password via Settings...
"""
        doc = parse_document("slice-meta.md", content)
        assert len(doc.slices) >= 1
        meta_slice = [s for s in doc.slices if s.slice_meta.get("question")]
        assert len(meta_slice) == 1
        assert meta_slice[0].slice_meta["question"] == "How to reset password?"
        assert meta_slice[0].slice_meta["category"] == "Account Security"
        assert "Users can reset password" in meta_slice[0].content

    def test_content_template_resolution(self):
        content = """---
title: Template Test
priority: P0
vector:
  content_template: "{doc.title} {body}"
---
Some body content.
"""
        doc = parse_document("template.md", content)
        assert len(doc.slices) == 1
        assert doc.slices[0].content_for_search == "Template Test Some body content."

    def test_label_placeholder_with_value(self):
        content = """---
title: Label Test
priority: P0
vector:
  content_template: "{级别：'doc.priority'} {body}"
---
Body here.
"""
        doc = parse_document("label.md", content)
        assert "级别：P0" in doc.slices[0].content_for_search

    def test_label_placeholder_without_value(self):
        content = """---
title: No Priority
vector:
  content_template: "{级别：'doc.priority'} {body}"
---
Body here.
"""
        doc = parse_document("label-empty.md", content)
        assert "级别" not in doc.slices[0].content_for_search
        assert "Body here" in doc.slices[0].content_for_search

    def test_toc_path_placeholder(self):
        content = """---
title: TOC Placeholder
vector:
  content_template: "{toc_path} {body}"
---
## Chapter 1
+++
### Section A
Section A content
"""
        doc = parse_document("toc-ph.md", content)
        section_slice = [s for s in doc.slices if "Section A content" in s.content]
        assert len(section_slice) == 1
        assert "Chapter 1 > Section A" in section_slice[0].content_for_search

    def test_toc_ancestors_placeholder_uses_parse_time_field(self):
        content = """---
title: Anc
vector:
  content_template: "{toc_ancestors} | {body}"
---
## Ch1
+++
### Sec
text
"""
        doc = parse_document("toc-anc-ph.md", content)
        section = [s for s in doc.slices if "text" in s.content][0]
        assert section.toc_ancestors == "Ch1"
        assert section.toc_path_joined == "Ch1 > Sec"
        assert "Ch1 | text" in section.content_for_search

    def test_source_field_preserved(self):
        content = """---
title: With Source
source: https://example.com/doc.pdf
---
Content.
"""
        doc = parse_document("source.md", content)
        assert doc.source_url == "https://example.com/doc.pdf"


class TestSchemaAwareNormalization:
    """§4.2.1 of the spec: arrays-typed fields are normalized to JSON arrays."""

    DOC_TYPES = {"tags": "keyword[]", "stakeholders": "keyword[]", "year_list": "integer[]", "title": "keyword"}

    def test_keyword_array_yaml_list_kept(self):
        content = """---
title: List form
tags:
  - 优先参考产品
  - QA
  - 货号
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert doc.doc_meta["tags"] == ["优先参考产品", "QA", "货号"]

    def test_keyword_array_inline_list_kept(self):
        content = """---
title: Inline
tags: [a, b]
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert doc.doc_meta["tags"] == ["a", "b"]

    def test_keyword_array_scalar_wrapped_into_single_element_list(self):
        """Single-token shortcut: scalar value becomes a one-element array."""
        content = """---
title: Scalar
tags: 优先参考产品
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert doc.doc_meta["tags"] == ["优先参考产品"]

    def test_keyword_array_csv_string_kept_as_single_token(self):
        """CSV string is NOT auto-split to avoid corrupting tags that contain commas."""
        content = """---
title: CSV
tags: "a,b"
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert doc.doc_meta["tags"] == ["a,b"]

    def test_keyword_array_empty_string_dropped(self):
        content = """---
title: Empty
tags: ""
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert "tags" not in doc.doc_meta

    def test_keyword_array_empty_list_dropped(self):
        content = """---
title: EmptyList
tags: []
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert "tags" not in doc.doc_meta

    def test_keyword_array_null_dropped(self):
        content = """---
title: Null
tags: null
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert "tags" not in doc.doc_meta

    def test_keyword_array_integer_value_coerced_to_string(self):
        content = """---
title: NumTag
tags: 2025
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert doc.doc_meta["tags"] == ["2025"]

    def test_integer_array_coerced(self):
        content = """---
title: Years
year_list: [2024, "2025", 2026]
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert doc.doc_meta["year_list"] == [2024, 2025, 2026]

    def test_non_array_field_untouched(self):
        """`title` is keyword, must not be wrapped into a list."""
        content = """---
title: Plain Title
---
body
"""
        doc = parse_document("a.md", content, doc_field_types=self.DOC_TYPES)
        assert doc.doc_meta["title"] == "Plain Title"

    def test_no_schema_keeps_legacy_behavior(self):
        """Without a schema the parser must not change values (back-compat)."""
        content = """---
title: Legacy
tags: 优先参考产品
---
body
"""
        doc = parse_document("a.md", content)
        assert doc.doc_meta["tags"] == "优先参考产品"

    def test_slice_field_types_normalize_slice_meta(self):
        content = """---
title: SliceArr
---
+++

<slice-meta>
```yaml slice-meta
labels: hot
```
</slice-meta>

body
"""
        doc = parse_document(
            "a.md",
            content,
            slice_field_types={"labels": "keyword[]"},
        )
        target = [s for s in doc.slices if s.slice_meta.get("labels") is not None]
        assert len(target) == 1
        assert target[0].slice_meta["labels"] == ["hot"]


class TestSchemaLoader:

    def test_get_field_definitions_cleaned_extracts_all_keys(self):
        from app.libs.doc_parser.schema_loader import get_field_definitions_cleaned

        schema = {
            "fields": [
                {"name": "status", "type": "enum", "values": ["draft", "approved"], "description": "Doc status"},
                {"name": "tags", "type": "keyword[]"},
                {"name": "author", "type": "keyword"},
                {"name": "count", "type": "integer"},
            ]
        }
        result = get_field_definitions_cleaned(schema)
        assert len(result) == 4
        assert result[0] == {"name": "status", "type": "enum", "values": ["draft", "approved"], "description": "Doc status"}
        assert result[1] == {"name": "tags", "type": "keyword[]"}
        assert result[2] == {"name": "author", "type": "keyword"}
        assert "values" not in result[2]

    def test_get_field_definitions_cleaned_defaults_type_to_keyword(self):
        from app.libs.doc_parser.schema_loader import get_field_definitions_cleaned

        schema = {"fields": [{"name": "title"}]}
        result = get_field_definitions_cleaned(schema)
        assert result[0]["type"] == "keyword"

    def test_get_field_definitions_cleaned_skips_no_name(self):
        from app.libs.doc_parser.schema_loader import get_field_definitions_cleaned

        schema = {"fields": [{"type": "keyword"}, {"name": "ok"}]}
        result = get_field_definitions_cleaned(schema)
        assert len(result) == 1
        assert result[0]["name"] == "ok"

    def test_get_field_definitions_cleaned_empty_fields(self):
        from app.libs.doc_parser.schema_loader import get_field_definitions_cleaned

        assert get_field_definitions_cleaned({}) == []
        assert get_field_definitions_cleaned({"fields": []}) == []

    def test_extract_schema_definitions_with_temp_dir(self, tmp_path):
        from app.libs.doc_parser.schema_loader import extract_schema_definitions

        schema_dir = tmp_path / "schema"
        schema_dir.mkdir()
        (schema_dir / "doc-meta.yaml").write_text(
            "fields:\n"
            "  - name: status\n"
            "    type: enum\n"
            "    values: [draft, approved]\n"
            "  - name: author\n"
            "    type: keyword\n"
        )
        (schema_dir / "slice-meta.yaml").write_text(
            "fields:\n"
            "  - name: question\n"
            "    type: keyword\n"
        )

        result = extract_schema_definitions(str(tmp_path))
        assert len(result["doc_meta_definitions"]) == 2
        assert result["doc_meta_definitions"][0]["name"] == "status"
        assert result["doc_meta_definitions"][0]["type"] == "enum"
        assert result["doc_meta_definitions"][0]["values"] == ["draft", "approved"]
        assert len(result["slice_meta_definitions"]) == 1
        assert result["slice_meta_definitions"][0]["name"] == "question"

    def test_extract_schema_definitions_missing_files(self, tmp_path):
        from app.libs.doc_parser.schema_loader import extract_schema_definitions

        result = extract_schema_definitions(str(tmp_path))
        assert result["doc_meta_definitions"] == []
        assert result["slice_meta_definitions"] == []
