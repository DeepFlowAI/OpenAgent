"""
Public (visitor-facing) Help Center schemas.

These schemas intentionally expose ONLY the white-listed fields needed for SEO
& visitor rendering. We never echo `tenant_id`, internal IDs of unrelated
resources, or knowledge-base internals.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict


class PublicTab(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    tab_slug: str
    sort_order: int


class PublicHelpCenterBundle(BaseModel):
    slug: str  # public_slug
    site_name: str
    publisher_logo_url: str | None
    tabs: list[PublicTab]


class PublicDocSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    file_path: str
    updated_at: Any | None = None


class PublicDocList(BaseModel):
    items: list[PublicDocSummary]
    total: int
    page: int
    per_page: int
    pages: int


class PublicDocDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    file_path: str
    markdown_content: str | None
    doc_meta: dict | None
    updated_at: Any | None = None
