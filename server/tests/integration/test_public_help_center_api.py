"""
Integration tests for the public (visitor-facing) Help Center API.

These tests cover only the visitor side; admin CRUD lives in
`test_help_center_api.py` / `test_help_center_tab_api.py`.
"""
import uuid

import pytest
from httpx import AsyncClient

import app.db.session as session_mod
from app.models.document import Document

from tests.conftest import make_auth_header


TENANT_ID = "T_TEST_PUBLIC_HC"
HEADERS = make_auth_header(TENANT_ID)


def _u(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ── Test fixtures (helpers that build a published Help Center) ──────────────


async def _make_kb(client: AsyncClient) -> int:
    payload = {
        "tenant_id": TENANT_ID,
        "name": _u("kb"),
        "git_url": "https://example.com/repo.git",
        "git_branch": "main",
        "auth_type": "none",
    }
    resp = await client.post("/api/v1/knowledge-bases", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_published_help_center(
    client: AsyncClient, slug: str, site_name: str = "Docs"
) -> int:
    """Create + publish a Help Center; returns its internal id."""
    create = await client.post(
        "/api/v1/help-centers", json={"name": _u("hc")}, headers=HEADERS
    )
    assert create.status_code == 201, create.text
    hc_id = create.json()["id"]

    publish = await client.put(
        f"/api/v1/help-centers/{hc_id}",
        json={"public_slug": slug, "site_name": site_name},
        headers=HEADERS,
    )
    assert publish.status_code == 200, publish.text
    return hc_id


async def _make_tab(
    client: AsyncClient,
    hc_id: int,
    kb_id: int,
    tab_slug: str,
    fixed_filters: list | None = None,
) -> int:
    resp = await client.post(
        f"/api/v1/help-centers/{hc_id}/tabs",
        json={
            "display_name": "Tab",
            "tab_slug": tab_slug,
            "knowledge_base_id": kb_id,
            "fixed_filters": fixed_filters or [],
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _seed_docs(kb_id: int, docs: list[dict]) -> list[int]:
    """Insert documents directly into the DB. Each item:
        {file_path, title?, description?, doc_meta?, markdown_content?}
    Returns the list of inserted ids."""
    ids: list[int] = []
    # Resolve the (possibly patched) session factory at call time so we use
    # the test engine that conftest installs into `session_mod`.
    async with session_mod.AsyncSessionLocal() as db:
        for d in docs:
            row = Document(
                knowledge_base_id=kb_id,
                tenant_id=TENANT_ID,
                title=d.get("title"),
                description=d.get("description"),
                file_path=d["file_path"],
                source_url=None,
                markdown_content=d.get("markdown_content"),
                doc_meta=d.get("doc_meta"),
                toc=None,
                slice_count=0,
                content_hash=None,
            )
            db.add(row)
            await db.flush()
            ids.append(row.id)
        await db.commit()
    return ids


# ── Tests ──────────────────────────────────────────────────────────────────


class TestPublicHelpCenterAPI:

    # 1. bundle resolution

    @pytest.mark.asyncio
    async def test_get_bundle_unpublished_returns_404(self, client: AsyncClient):
        slug = _u("unp")
        # Create but DON'T set public_slug — should be invisible to visitors.
        await client.post(
            "/api/v1/help-centers", json={"name": _u("hc")}, headers=HEADERS
        )
        resp = await client.get(f"/api/v1/public/help-centers/{slug}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_bundle_published_returns_200(self, client: AsyncClient):
        slug = _u("pub")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug, "My Docs")
        await _make_tab(client, hc_id, kb_id, _u("guide"))

        resp = await client.get(f"/api/v1/public/help-centers/{slug}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == slug
        assert body["site_name"] == "My Docs"
        assert len(body["tabs"]) == 1
        assert "tenant_id" not in body  # leak check

    @pytest.mark.asyncio
    async def test_get_bundle_no_auth_required(self, client: AsyncClient):
        """Public API must work without any Authorization header."""
        slug = _u("noauth")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug)
        await _make_tab(client, hc_id, kb_id, _u("t"))

        resp = await client.get(f"/api/v1/public/help-centers/{slug}")
        assert resp.status_code == 200

    # 2. list docs

    @pytest.mark.asyncio
    async def test_list_docs_returns_only_filtered(self, client: AsyncClient):
        slug = _u("filtered")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug)
        tab_slug = _u("faq")
        await _make_tab(
            client,
            hc_id,
            kb_id,
            tab_slug,
            fixed_filters=[{"field": "category", "op": "eq", "value": "faq"}],
        )

        await _seed_docs(
            kb_id,
            [
                {
                    "file_path": "faq/a.md",
                    "title": "A",
                    "doc_meta": {"category": "faq"},
                    "markdown_content": "# A",
                },
                {
                    "file_path": "faq/b.md",
                    "title": "B",
                    "doc_meta": {"category": "faq"},
                    "markdown_content": "# B",
                },
                {
                    # Should be excluded — different category.
                    "file_path": "guide/c.md",
                    "title": "C",
                    "doc_meta": {"category": "guide"},
                    "markdown_content": "# C",
                },
            ],
        )

        resp = await client.get(
            f"/api/v1/public/help-centers/{slug}/tabs/{tab_slug}/docs"
        )
        assert resp.status_code == 200
        body = resp.json()
        titles = sorted(d["title"] for d in body["items"])
        assert titles == ["A", "B"]
        assert body["total"] == 2

    @pytest.mark.asyncio
    async def test_list_docs_unknown_tab_returns_404(self, client: AsyncClient):
        slug = _u("ut")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug)
        await _make_tab(client, hc_id, kb_id, _u("real"))

        resp = await client.get(
            f"/api/v1/public/help-centers/{slug}/tabs/missing/docs"
        )
        assert resp.status_code == 404

    # 3. get doc

    @pytest.mark.asyncio
    async def test_get_doc_with_nested_path_returns_200(
        self, client: AsyncClient
    ):
        slug = _u("nested")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug)
        tab_slug = _u("docs")
        await _make_tab(client, hc_id, kb_id, tab_slug)

        await _seed_docs(
            kb_id,
            [
                {
                    "file_path": "guide/getting-started.md",
                    "title": "Getting Started",
                    "markdown_content": "# Hello\n\nThis is the body.",
                }
            ],
        )

        resp = await client.get(
            f"/api/v1/public/help-centers/{slug}/tabs/{tab_slug}"
            "/docs/guide/getting-started.md"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["title"] == "Getting Started"
        assert "Hello" in body["markdown_content"]

    @pytest.mark.asyncio
    async def test_get_doc_outside_filter_returns_404(self, client: AsyncClient):
        """A doc that exists in the KB but doesn't satisfy the tab's
        fixed_filters must NOT be visible through this tab."""
        slug = _u("outside")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug)
        tab_slug = _u("only-faq")
        await _make_tab(
            client,
            hc_id,
            kb_id,
            tab_slug,
            fixed_filters=[{"field": "category", "op": "eq", "value": "faq"}],
        )

        await _seed_docs(
            kb_id,
            [
                {
                    "file_path": "guide/c.md",
                    "title": "C",
                    "doc_meta": {"category": "guide"},
                }
            ],
        )

        resp = await client.get(
            f"/api/v1/public/help-centers/{slug}/tabs/{tab_slug}/docs/guide/c.md"
        )
        assert resp.status_code == 404

    # 3.b numeric / date fixed filters — type-aware comparison

    @pytest.mark.asyncio
    async def test_list_docs_numeric_gt_uses_numeric_compare(
        self, client: AsyncClient
    ):
        """Lexical comparison would order '10' < '9'; numeric comparison must
        place 10 above 9. This test pins the type-aware behaviour."""
        slug = _u("num")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug)
        tab_slug = _u("priced")
        await _make_tab(
            client,
            hc_id,
            kb_id,
            tab_slug,
            fixed_filters=[{"field": "price", "op": "gt", "value": 9}],
        )

        await _seed_docs(
            kb_id,
            [
                {"file_path": "p9.md", "title": "Nine", "doc_meta": {"price": 9}},
                {"file_path": "p10.md", "title": "Ten", "doc_meta": {"price": 10}},
                {"file_path": "p100.md", "title": "Hundred", "doc_meta": {"price": 100}},
            ],
        )

        resp = await client.get(
            f"/api/v1/public/help-centers/{slug}/tabs/{tab_slug}/docs"
        )
        assert resp.status_code == 200
        titles = sorted(d["title"] for d in resp.json()["items"])
        assert titles == ["Hundred", "Ten"]

    @pytest.mark.asyncio
    async def test_list_docs_invalid_date_value_does_not_crash(
        self, client: AsyncClient
    ):
        """A filter value shaped like a date but invalid (e.g. Feb 31) must
        not 500 the visitor API. It should degrade to an empty result."""
        slug = _u("baddate")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug)
        tab_slug = _u("invalid")
        await _make_tab(
            client,
            hc_id,
            kb_id,
            tab_slug,
            fixed_filters=[
                {"field": "published_at", "op": "ge", "value": "2026-02-31"}
            ],
        )

        await _seed_docs(
            kb_id,
            [
                {
                    "file_path": "x.md",
                    "title": "X",
                    "doc_meta": {"published_at": "2026-03-01"},
                }
            ],
        )

        resp = await client.get(
            f"/api/v1/public/help-centers/{slug}/tabs/{tab_slug}/docs"
        )
        assert resp.status_code == 200
        # Invalid date filter degrades to text comparison; gt/ge fall through
        # to false() in that path, so result is empty rather than an error.
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_list_docs_date_ge_uses_date_compare(
        self, client: AsyncClient
    ):
        slug = _u("date")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug)
        tab_slug = _u("recent")
        await _make_tab(
            client,
            hc_id,
            kb_id,
            tab_slug,
            fixed_filters=[
                {"field": "published_at", "op": "ge", "value": "2026-01-01"}
            ],
        )

        await _seed_docs(
            kb_id,
            [
                {
                    "file_path": "old.md",
                    "title": "Old",
                    "doc_meta": {"published_at": "2025-12-31"},
                },
                {
                    "file_path": "new.md",
                    "title": "New",
                    "doc_meta": {"published_at": "2026-02-15"},
                },
                {
                    # Missing field should be excluded by ge.
                    "file_path": "no.md",
                    "title": "No",
                    "doc_meta": {},
                },
            ],
        )

        resp = await client.get(
            f"/api/v1/public/help-centers/{slug}/tabs/{tab_slug}/docs"
        )
        assert resp.status_code == 200
        titles = [d["title"] for d in resp.json()["items"]]
        assert titles == ["New"]

    # 4. sitemap

    @pytest.mark.asyncio
    async def test_sitemap_returns_xml_with_all_urls(self, client: AsyncClient):
        slug = _u("sm")
        kb_id = await _make_kb(client)
        hc_id = await _make_published_help_center(client, slug)
        tab_slug = _u("t")
        await _make_tab(client, hc_id, kb_id, tab_slug)

        await _seed_docs(
            kb_id,
            [
                {"file_path": "a.md", "title": "A", "markdown_content": ""},
                {"file_path": "b.md", "title": "B", "markdown_content": ""},
            ],
        )

        resp = await client.get(
            f"/api/v1/public/help-centers/{slug}/sitemap.xml"
        )
        assert resp.status_code == 200
        assert "application/xml" in resp.headers["content-type"]
        body = resp.text
        # Site root + tab root + 2 docs = 4 <url> tags
        assert body.count("<url>") == 4
        assert f"/hc/{slug}" in body
        assert "a.md" in body and "b.md" in body
