"""
Integration tests for Help Center API.
"""
import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import make_auth_header


TENANT_ID = "T_TEST_HC"
OTHER_TENANT_ID = "T_TEST_HC_OTHER"
HEADERS = make_auth_header(TENANT_ID)
OTHER_HEADERS = make_auth_header(OTHER_TENANT_ID)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _create(client: AsyncClient, name_prefix: str = "hc") -> int:
    """Helper: create a fresh Help Center for the default tenant."""
    resp = await client.post(
        "/api/v1/help-centers",
        json={"name": _unique(name_prefix), "description": "desc"},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestHelpCenterAPI:

    @pytest.mark.asyncio
    async def test_list_returns_200(self, client: AsyncClient):
        resp = await client.get("/api/v1/help-centers", headers=HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body and "per_page" in body and "pages" in body

    @pytest.mark.asyncio
    async def test_create_with_valid_data_returns_201(self, client: AsyncClient):
        name = _unique("hc-create")
        resp = await client.post(
            "/api/v1/help-centers",
            json={"name": name, "description": "hello"},
            headers=HEADERS,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == name
        assert body["description"] == "hello"
        assert body["public_slug"] is None
        assert body["site_name"] is None
        assert body["publisher_logo_url"] is None
        assert body["public_root_url"] is None

    @pytest.mark.asyncio
    async def test_create_with_empty_name_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/help-centers", json={"name": ""}, headers=HEADERS
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_too_long_name_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/help-centers",
            json={"name": "x" * 65},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_existing_returns_200(self, client: AsyncClient):
        hc_id = await _create(client)
        resp = await client.get(f"/api/v1/help-centers/{hc_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["id"] == hc_id

    @pytest.mark.asyncio
    async def test_get_not_found_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/help-centers/99999999", headers=HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_other_tenant_returns_404(self, client: AsyncClient):
        hc_id = await _create(client)
        resp = await client.get(
            f"/api/v1/help-centers/{hc_id}", headers=OTHER_HEADERS
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_basic_info_returns_200(self, client: AsyncClient):
        hc_id = await _create(client)
        resp = await client.put(
            f"/api/v1/help-centers/{hc_id}",
            json={"description": "new desc"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "new desc"

    @pytest.mark.asyncio
    async def test_update_with_valid_slug_returns_200_and_root_url(
        self, client: AsyncClient
    ):
        hc_id = await _create(client)
        slug = _unique("slug").lower()
        resp = await client.put(
            f"/api/v1/help-centers/{hc_id}",
            json={"public_slug": slug, "site_name": "My Docs"},
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["public_slug"] == slug
        assert body["site_name"] == "My Docs"
        assert body["public_root_url"] is not None
        assert body["public_root_url"].endswith(f"/hc/{slug}")
        assert body["public_root_url"].startswith("https://")

    @pytest.mark.asyncio
    async def test_update_with_invalid_slug_format_returns_422(
        self, client: AsyncClient
    ):
        hc_id = await _create(client)
        resp = await client.put(
            f"/api/v1/help-centers/{hc_id}",
            json={"public_slug": "Invalid_Slug!"},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_with_too_short_slug_returns_422(
        self, client: AsyncClient
    ):
        hc_id = await _create(client)
        resp = await client.put(
            f"/api/v1/help-centers/{hc_id}",
            json={"public_slug": "ab"},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_slug_set_but_site_name_missing_returns_400(
        self, client: AsyncClient
    ):
        hc_id = await _create(client)
        resp = await client.put(
            f"/api/v1/help-centers/{hc_id}",
            json={"public_slug": _unique("ns").lower()},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert "site_name" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_update_with_duplicate_slug_returns_409(
        self, client: AsyncClient
    ):
        slug = _unique("dup").lower()

        hc1 = await _create(client, "hc-dup1")
        r1 = await client.put(
            f"/api/v1/help-centers/{hc1}",
            json={"public_slug": slug, "site_name": "Site A"},
            headers=HEADERS,
        )
        assert r1.status_code == 200, r1.text

        hc2 = await _create(client, "hc-dup2")
        r2 = await client.put(
            f"/api/v1/help-centers/{hc2}",
            json={"public_slug": slug, "site_name": "Site B"},
            headers=HEADERS,
        )
        assert r2.status_code == 409

    @pytest.mark.asyncio
    async def test_slug_is_globally_unique_across_tenants(
        self, client: AsyncClient
    ):
        """Slug must collide across tenants — visitor URL lives on a single
        shared host, so two tenants picking the same slug would be ambiguous."""
        slug = _unique("crosstenant").lower()

        hc1 = await _create(client, "hc-cross-a")
        r1 = await client.put(
            f"/api/v1/help-centers/{hc1}",
            json={"public_slug": slug, "site_name": "Site A"},
            headers=HEADERS,
        )
        assert r1.status_code == 200, r1.text

        # Different tenant — must still collide.
        resp = await client.post(
            "/api/v1/help-centers",
            json={"name": _unique("hc-cross-b"), "description": ""},
            headers=OTHER_HEADERS,
        )
        assert resp.status_code == 201
        hc2 = resp.json()["id"]
        r2 = await client.put(
            f"/api/v1/help-centers/{hc2}",
            json={"public_slug": slug, "site_name": "Site B"},
            headers=OTHER_HEADERS,
        )
        assert r2.status_code == 409

        # And the public availability check on the OTHER tenant should
        # see the slug as taken too.
        resp = await client.get(
            f"/api/v1/help-centers/check-slug?slug={slug}",
            headers=OTHER_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    @pytest.mark.asyncio
    async def test_check_slug_returns_available_when_unused(
        self, client: AsyncClient
    ):
        slug = _unique("avail").lower()
        resp = await client.get(
            f"/api/v1/help-centers/check-slug?slug={slug}", headers=HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["available"] is True

    @pytest.mark.asyncio
    async def test_check_slug_returns_unavailable_when_taken(
        self, client: AsyncClient
    ):
        slug = _unique("taken").lower()
        hc_id = await _create(client, "hc-taken")
        await client.put(
            f"/api/v1/help-centers/{hc_id}",
            json={"public_slug": slug, "site_name": "Taken"},
            headers=HEADERS,
        )

        resp = await client.get(
            f"/api/v1/help-centers/check-slug?slug={slug}", headers=HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    @pytest.mark.asyncio
    async def test_check_slug_excludes_self(self, client: AsyncClient):
        slug = _unique("self").lower()
        hc_id = await _create(client, "hc-self")
        await client.put(
            f"/api/v1/help-centers/{hc_id}",
            json={"public_slug": slug, "site_name": "Self"},
            headers=HEADERS,
        )

        resp = await client.get(
            f"/api/v1/help-centers/check-slug?slug={slug}&exclude_id={hc_id}",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["available"] is True

    @pytest.mark.asyncio
    async def test_check_slug_ignores_foreign_tenant_exclude_id(
        self, client: AsyncClient
    ):
        """`exclude_id` must only suppress the caller's own row. Passing a
        Help Center id from another tenant must be silently dropped so the
        slug stays reported as taken."""
        slug = _unique("foreign").lower()

        hc_a = await _create(client, "hc-foreign-a")
        r1 = await client.put(
            f"/api/v1/help-centers/{hc_a}",
            json={"public_slug": slug, "site_name": "A"},
            headers=HEADERS,
        )
        assert r1.status_code == 200, r1.text

        # Tenant B asks: "is this slug available if I'm updating row hc_a?"
        # hc_a doesn't belong to B, so the exclude must be ignored and the
        # answer must remain `unavailable`.
        resp = await client.get(
            f"/api/v1/help-centers/check-slug?slug={slug}&exclude_id={hc_a}",
            headers=OTHER_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    @pytest.mark.asyncio
    async def test_delete_returns_200(self, client: AsyncClient):
        hc_id = await _create(client, "hc-del")
        resp = await client.delete(
            f"/api/v1/help-centers/{hc_id}", headers=HEADERS
        )
        assert resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/help-centers/{hc_id}", headers=HEADERS
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_other_tenant_returns_404(self, client: AsyncClient):
        hc_id = await _create(client, "hc-cross")
        resp = await client.delete(
            f"/api/v1/help-centers/{hc_id}", headers=OTHER_HEADERS
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/help-centers")
        assert resp.status_code == 401
