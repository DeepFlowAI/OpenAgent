"""
Schema loader — reads schema/doc-meta.yaml and schema/slice-meta.yaml from a repo.
"""
import os
from typing import Any

import yaml


def load_schema(repo_dir: str, filename: str) -> dict[str, Any]:
    """Load a YAML schema file from schema/ directory. Returns field definitions."""
    path = os.path.join(repo_dir, "schema", filename)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def get_field_definitions(schema_data: dict) -> list[dict]:
    """Extract field list from a schema dict."""
    return schema_data.get("fields", [])


def get_field_type_map(schema_data: dict) -> dict[str, str]:
    """Return {field_name: semantic_type} mapping."""
    fields = get_field_definitions(schema_data)
    return {f["name"]: f.get("type", "keyword") for f in fields if "name" in f}


def get_field_names(schema_data: dict) -> list[str]:
    """Return sorted list of field names from a schema dict."""
    fields = get_field_definitions(schema_data)
    return sorted(f["name"] for f in fields if "name" in f)


def get_field_definitions_cleaned(schema_data: dict) -> list[dict]:
    """Return sanitised field definition dicts suitable for JSON storage.

    Each dict contains at least ``name`` and ``type`` (defaulting to
    ``"keyword"``).  Optional keys such as ``values`` and ``description``
    are included when present in the source YAML.
    """
    raw_fields = get_field_definitions(schema_data)
    result: list[dict] = []
    for f in raw_fields:
        if "name" not in f:
            continue
        cleaned: dict[str, Any] = {
            "name": f["name"],
            "type": f.get("type", "keyword"),
        }
        if "values" in f and isinstance(f["values"], list):
            cleaned["values"] = f["values"]
        if "description" in f and isinstance(f["description"], str):
            cleaned["description"] = f["description"]
        result.append(cleaned)
    return result


def extract_schema_fields(repo_dir: str) -> dict[str, list[str]]:
    """Load both schema files and return {doc_meta: [...], slice_meta: [...]} field name lists."""
    doc_schema = load_schema(repo_dir, "doc-meta.yaml")
    slice_schema = load_schema(repo_dir, "slice-meta.yaml")
    return {
        "doc_meta": get_field_names(doc_schema),
        "slice_meta": get_field_names(slice_schema),
    }


def extract_schema_definitions(repo_dir: str) -> dict[str, list[dict]]:
    """Load both schema files and return full field definitions.

    Returns ``{doc_meta_definitions: [...], slice_meta_definitions: [...]}``
    where each item is a dict with ``name``, ``type``, and optional
    ``values`` / ``description``.
    """
    doc_schema = load_schema(repo_dir, "doc-meta.yaml")
    slice_schema = load_schema(repo_dir, "slice-meta.yaml")
    return {
        "doc_meta_definitions": get_field_definitions_cleaned(doc_schema),
        "slice_meta_definitions": get_field_definitions_cleaned(slice_schema),
    }
