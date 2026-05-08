"""
Unit tests for sync service helper functions: hash computation and file classification.
"""
import hashlib
import os
import tempfile

import pytest

from app.services.sync_service import (
    _compute_schema_hash,
    _compute_content_hash,
    _classify_files,
)


class TestComputeContentHash:

    def test_deterministic(self):
        h1 = _compute_content_hash("hello world")
        h2 = _compute_content_hash("hello world")
        assert h1 == h2

    def test_sha256_format(self):
        h = _compute_content_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_content_different_hash(self):
        h1 = _compute_content_hash("aaa")
        h2 = _compute_content_hash("bbb")
        assert h1 != h2

    def test_empty_string(self):
        h = _compute_content_hash("")
        expected = hashlib.sha256(b"").hexdigest()
        assert h == expected


class TestComputeSchemaHash:

    def test_with_both_files(self):
        with tempfile.TemporaryDirectory() as repo:
            schema_dir = os.path.join(repo, "schema")
            os.makedirs(schema_dir)
            with open(os.path.join(schema_dir, "doc-meta.yaml"), "w") as f:
                f.write("fields:\n  - name: title\n")
            with open(os.path.join(schema_dir, "slice-meta.yaml"), "w") as f:
                f.write("fields:\n  - name: content\n")

            h = _compute_schema_hash(repo)
            assert len(h) == 64

    def test_missing_files_still_produces_hash(self):
        with tempfile.TemporaryDirectory() as repo:
            h = _compute_schema_hash(repo)
            assert len(h) == 64

    def test_content_change_changes_hash(self):
        with tempfile.TemporaryDirectory() as repo:
            schema_dir = os.path.join(repo, "schema")
            os.makedirs(schema_dir)
            with open(os.path.join(schema_dir, "doc-meta.yaml"), "w") as f:
                f.write("v1")
            with open(os.path.join(schema_dir, "slice-meta.yaml"), "w") as f:
                f.write("v1")
            h1 = _compute_schema_hash(repo)

            with open(os.path.join(schema_dir, "doc-meta.yaml"), "w") as f:
                f.write("v2")
            h2 = _compute_schema_hash(repo)
            assert h1 != h2

    def test_same_content_same_hash(self):
        with tempfile.TemporaryDirectory() as repo:
            schema_dir = os.path.join(repo, "schema")
            os.makedirs(schema_dir)
            with open(os.path.join(schema_dir, "doc-meta.yaml"), "w") as f:
                f.write("same")
            with open(os.path.join(schema_dir, "slice-meta.yaml"), "w") as f:
                f.write("same")
            h1 = _compute_schema_hash(repo)
            h2 = _compute_schema_hash(repo)
            assert h1 == h2


class TestClassifyFiles:

    def test_all_new(self):
        discovered = {"a.md": "h1", "b.md": "h2"}
        existing: dict = {}
        added, modified, unchanged, deleted = _classify_files(discovered, existing)
        assert sorted(added) == ["a.md", "b.md"]
        assert modified == []
        assert unchanged == []
        assert deleted == []

    def test_all_unchanged(self):
        discovered = {"a.md": "h1", "b.md": "h2"}
        existing = {"a.md": (1, "h1"), "b.md": (2, "h2")}
        added, modified, unchanged, deleted = _classify_files(discovered, existing)
        assert added == []
        assert modified == []
        assert sorted(unchanged) == ["a.md", "b.md"]
        assert deleted == []

    def test_mixed(self):
        discovered = {"a.md": "h1_new", "c.md": "h3"}
        existing = {"a.md": (1, "h1_old"), "b.md": (2, "h2")}
        added, modified, unchanged, deleted = _classify_files(discovered, existing)
        assert added == ["c.md"]
        assert modified == ["a.md"]
        assert unchanged == []
        assert deleted == ["b.md"]

    def test_null_hash_treated_as_modified(self):
        discovered = {"a.md": "h1"}
        existing = {"a.md": (1, None)}
        added, modified, unchanged, deleted = _classify_files(discovered, existing)
        assert added == []
        assert modified == ["a.md"]
        assert unchanged == []
        assert deleted == []

    def test_empty_both(self):
        added, modified, unchanged, deleted = _classify_files({}, {})
        assert added == []
        assert modified == []
        assert unchanged == []
        assert deleted == []

    def test_all_deleted(self):
        discovered: dict = {}
        existing = {"a.md": (1, "h1"), "b.md": (2, "h2")}
        added, modified, unchanged, deleted = _classify_files(discovered, existing)
        assert added == []
        assert modified == []
        assert unchanged == []
        assert sorted(deleted) == ["a.md", "b.md"]
