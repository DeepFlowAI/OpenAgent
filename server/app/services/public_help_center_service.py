"""
Public Help Center service — visitor-facing orchestration.

A Help Center is "published" when it has a non-null `public_slug` AND a
non-null `site_name`. Anything that's not fully published returns 404 to
visitors.
"""
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import NotFoundError
from app.models.document import Document
from app.models.help_center import HelpCenter
from app.models.help_center_tab import HelpCenterTab
from app.repositories.public_help_center_repository import (
    PublicHelpCenterRepository,
)


def _is_published(hc: HelpCenter | None) -> bool:
    return bool(hc and hc.public_slug and hc.site_name)


def _doc_summary(d: Document) -> dict:
    return {
        "id": d.id,
        "title": d.title or _title_from_path(d.file_path),
        "description": d.description,
        "file_path": d.file_path,
        "updated_at": d.updated_at,
    }


def _doc_detail(d: Document) -> dict:
    return {
        "id": d.id,
        "title": d.title or _title_from_path(d.file_path),
        "description": d.description,
        "file_path": d.file_path,
        "markdown_content": d.markdown_content,
        "doc_meta": d.doc_meta,
        "updated_at": d.updated_at,
    }


def _title_from_path(file_path: str) -> str:
    """Best-effort fallback when a doc has no title — strip directories and
    trailing `.md` for display only."""
    last = file_path.rsplit("/", 1)[-1]
    if last.endswith(".md"):
        last = last[:-3]
    return last or file_path


def _encode_doc_path(file_path: str) -> str:
    """URL-encode each path segment but keep `/` separators."""
    return "/".join(quote(p, safe="") for p in file_path.split("/"))


class PublicHelpCenterService:

    @staticmethod
    async def get_bundle(db: AsyncSession, slug: str) -> dict:
        hc = await PublicHelpCenterRepository.get_by_public_slug(db, slug)
        if not _is_published(hc):
            raise NotFoundError("help_center_not_published")
        tabs = await PublicHelpCenterRepository.list_tabs(db, hc.id)
        return {
            "slug": hc.public_slug,
            "site_name": hc.site_name,
            "publisher_logo_url": hc.publisher_logo_url,
            "tabs": [
                {
                    "id": t.id,
                    "display_name": t.display_name,
                    "tab_slug": t.tab_slug,
                    "sort_order": t.sort_order,
                }
                for t in tabs
            ],
        }

    @staticmethod
    async def _resolve_tab(
        db: AsyncSession, slug: str, tab_slug: str
    ) -> tuple[HelpCenter, HelpCenterTab]:
        hc = await PublicHelpCenterRepository.get_by_public_slug(db, slug)
        if not _is_published(hc):
            raise NotFoundError("help_center_not_published")
        tab = await PublicHelpCenterRepository.get_tab_by_slug(
            db, hc.id, tab_slug
        )
        if not tab:
            raise NotFoundError("tab_not_found")
        return hc, tab

    @staticmethod
    async def list_docs(
        db: AsyncSession,
        slug: str,
        tab_slug: str,
        page: int,
        per_page: int,
    ) -> dict:
        _, tab = await PublicHelpCenterService._resolve_tab(db, slug, tab_slug)
        docs, total = await PublicHelpCenterRepository.list_docs_for_tab(
            db, tab, page, per_page
        )
        nav = await PublicHelpCenterRepository.get_nav_config_for_tab(db, tab)
        pages = (total + per_page - 1) // per_page if per_page > 0 else 1
        return {
            "items": [_doc_summary(d) for d in docs],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "nav": nav,
        }

    @staticmethod
    async def get_doc(
        db: AsyncSession, slug: str, tab_slug: str, doc_path: str
    ) -> dict:
        _, tab = await PublicHelpCenterService._resolve_tab(db, slug, tab_slug)
        doc = await PublicHelpCenterRepository.get_doc_by_path_for_tab(
            db, tab, doc_path
        )
        if not doc:
            raise NotFoundError("document_not_found")
        return _doc_detail(doc)

    @staticmethod
    async def render_sitemap(db: AsyncSession, slug: str) -> str:
        hc = await PublicHelpCenterRepository.get_by_public_slug(db, slug)
        if not _is_published(hc):
            raise NotFoundError("help_center_not_published")
        tabs = await PublicHelpCenterRepository.list_tabs(db, hc.id)

        host = settings.PUBLIC_DOCS_HOST.rstrip("/")
        base = f"https://{host}/hc/{quote(hc.public_slug, safe='')}"

        urls: list[tuple[str, str | None]] = [(base, None)]

        for t in tabs:
            tab_url = f"{base}/t/{quote(t.tab_slug, safe='')}"
            urls.append((tab_url, None))
            docs = await PublicHelpCenterRepository.list_all_docs_for_sitemap(
                db, t
            )
            for d in docs:
                doc_url = f"{tab_url}/{_encode_doc_path(d.file_path)}"
                lastmod = (
                    d.updated_at.strftime("%Y-%m-%d") if d.updated_at else None
                )
                urls.append((doc_url, lastmod))

        return _render_sitemap_xml(urls)


def _render_sitemap_xml(urls: list[tuple[str, str | None]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines)
