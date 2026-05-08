"""
Integration tests for Help Center Tab API.
"""
import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import make_auth_header


TENANT_ID = "T_TEST_HC_TAB"
OTHER_TENANT_ID = "T_TEST_HC_TAB_OTHER"
HEADERS = make_auth_header(TENANT_ID)
OTHER_HEADERS = make_auth_header(OTHER_TENANT_ID)


def _u(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _make_kb(client: AsyncClient, tenant_id: str = TENANT_ID) -> int:
    """Create a KB owned by the given tenant. The KB API uses query-param
    tenant scoping, not Bearer auth, hence no headers needed."""
    payload = {
        "tenant_id": tenant_id,
        "name": _u("kb"),
        "git_url": "https://example.com/repo.git",
        "git_branch": "main",
        "auth_type": "none",
    }
    resp = await client.post("/api/v1/knowledge-bases", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_help_center(client: AsyncClient) -> int:
    resp = await client.post(
        "/api/v1/help-centers",
        json={"name": _u("hc")},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestHelpCenterTabAPI:

    # ── create / list ──

    @pytest.mark.asyncio
    async def test_create_with_auto_slug_returns_201(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)

        resp = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={
                "display_name": "用户指南",
                "knowledge_base_id": kb_id,
                "fixed_filters": [],
            },
            headers=HEADERS,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["display_name"] == "用户指南"
        assert body["tab_slug"] is not None
        assert body["tab_slug"].startswith("t-")
        assert body["sort_order"] == 0
        assert body["fixed_filters"] == []

    @pytest.mark.asyncio
    async def test_create_with_custom_slug_returns_201(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        slug = _u("guide").lower()

        resp = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={
                "display_name": "API",
                "tab_slug": slug,
                "knowledge_base_id": kb_id,
            },
            headers=HEADERS,
        )
        assert resp.status_code == 201
        assert resp.json()["tab_slug"] == slug

    @pytest.mark.asyncio
    async def test_create_with_invalid_slug_returns_422(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)

        resp = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={
                "display_name": "X",
                "tab_slug": "Bad_Slug!",
                "knowledge_base_id": kb_id,
            },
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_duplicate_slug_returns_409(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        slug = _u("dup").lower()

        r1 = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={"display_name": "A", "tab_slug": slug, "knowledge_base_id": kb_id},
            headers=HEADERS,
        )
        assert r1.status_code == 201

        r2 = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={"display_name": "B", "tab_slug": slug, "knowledge_base_id": kb_id},
            headers=HEADERS,
        )
        assert r2.status_code == 409

    @pytest.mark.asyncio
    async def test_create_with_kb_from_other_tenant_returns_400(
        self, client: AsyncClient
    ):
        hc_id = await _make_help_center(client)
        other_kb = await _make_kb(client, tenant_id=OTHER_TENANT_ID)

        resp = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={
                "display_name": "X",
                "knowledge_base_id": other_kb,
            },
            headers=HEADERS,
        )
        # Service raises ValidationError → maps to 400.
        assert resp.status_code == 400
        assert "knowledge_base_invalid" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_create_with_invalid_filter_op_returns_422(
        self, client: AsyncClient
    ):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)

        resp = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={
                "display_name": "X",
                "knowledge_base_id": kb_id,
                "fixed_filters": [
                    {"field": "x", "op": "BAD_OP", "value": 1}
                ],
            },
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_in_filter_with_non_list_value_returns_422(
        self, client: AsyncClient
    ):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)

        resp = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={
                "display_name": "X",
                "knowledge_base_id": kb_id,
                "fixed_filters": [
                    {"field": "x", "op": "in", "value": "not-a-list"}
                ],
            },
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_returns_tabs_in_sort_order(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)

        for name in ["A", "B", "C"]:
            await client.post(
                f"/api/v1/help-centers/{hc_id}/tabs",
                json={"display_name": name, "knowledge_base_id": kb_id},
                headers=HEADERS,
            )

        resp = await client.get(
            f"/api/v1/help-centers/{hc_id}/tabs", headers=HEADERS
        )
        assert resp.status_code == 200
        names = [item["display_name"] for item in resp.json()["items"]]
        assert names == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_list_includes_kb_name(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={"display_name": "X", "knowledge_base_id": kb_id},
            headers=HEADERS,
        )
        resp = await client.get(
            f"/api/v1/help-centers/{hc_id}/tabs", headers=HEADERS
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items[0]["knowledge_base_name"] is not None

    @pytest.mark.asyncio
    async def test_list_other_tenant_returns_404(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        resp = await client.get(
            f"/api/v1/help-centers/{hc_id}/tabs", headers=OTHER_HEADERS
        )
        assert resp.status_code == 404

    # ── update ──

    @pytest.mark.asyncio
    async def test_update_display_name_returns_200(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        c = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={"display_name": "Old", "knowledge_base_id": kb_id},
            headers=HEADERS,
        )
        tab_id = c.json()["id"]

        resp = await client.put(
            f"/api/v1/help-centers/{hc_id}/tabs/{tab_id}",
            json={"display_name": "New"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "New"

    @pytest.mark.asyncio
    async def test_update_filters_returns_200(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        c = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={"display_name": "X", "knowledge_base_id": kb_id},
            headers=HEADERS,
        )
        tab_id = c.json()["id"]

        new_filters = [
            {"field": "category", "op": "eq", "value": "guide"},
            {"field": "version", "op": "in", "value": ["1.0", "1.1"]},
        ]
        resp = await client.put(
            f"/api/v1/help-centers/{hc_id}/tabs/{tab_id}",
            json={"fixed_filters": new_filters},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["fixed_filters"] == new_filters

    @pytest.mark.asyncio
    async def test_update_tab_id_not_under_help_center_returns_404(
        self, client: AsyncClient
    ):
        hc_a = await _make_help_center(client)
        hc_b = await _make_help_center(client)
        kb_id = await _make_kb(client)
        c = await client.post(
            f"/api/v1/help-centers/{hc_a}/tabs",
            json={"display_name": "X", "knowledge_base_id": kb_id},
            headers=HEADERS,
        )
        tab_id = c.json()["id"]

        resp = await client.put(
            f"/api/v1/help-centers/{hc_b}/tabs/{tab_id}",
            json={"display_name": "Y"},
            headers=HEADERS,
        )
        assert resp.status_code == 404

    # ── delete ──

    @pytest.mark.asyncio
    async def test_delete_returns_200(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        c = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={"display_name": "X", "knowledge_base_id": kb_id},
            headers=HEADERS,
        )
        tab_id = c.json()["id"]

        resp = await client.delete(
            f"/api/v1/help-centers/{hc_id}/tabs/{tab_id}", headers=HEADERS
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_via_help_center_cascades(self, client: AsyncClient):
        """ON DELETE CASCADE: removing a Help Center removes its tabs."""
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={"display_name": "X", "knowledge_base_id": kb_id},
            headers=HEADERS,
        )

        delete_resp = await client.delete(
            f"/api/v1/help-centers/{hc_id}", headers=HEADERS
        )
        assert delete_resp.status_code == 200

        # Help Center is gone; subsequent list call returns 404.
        list_resp = await client.get(
            f"/api/v1/help-centers/{hc_id}/tabs", headers=HEADERS
        )
        assert list_resp.status_code == 404

    # ── reorder ──

    @pytest.mark.asyncio
    async def test_reorder_updates_sort_order(self, client: AsyncClient):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        ids: list[int] = []
        for name in ["A", "B", "C"]:
            r = await client.post(
                f"/api/v1/help-centers/{hc_id}/tabs",
                json={"display_name": name, "knowledge_base_id": kb_id},
                headers=HEADERS,
            )
            ids.append(r.json()["id"])

        # Reverse the order.
        new_order = list(reversed(ids))
        resp = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs/reorder",
            json={"tab_ids": new_order},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        returned_ids = [item["id"] for item in resp.json()["items"]]
        assert returned_ids == new_order

    @pytest.mark.asyncio
    async def test_reorder_with_missing_tab_returns_400(
        self, client: AsyncClient
    ):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        ids: list[int] = []
        for name in ["A", "B"]:
            r = await client.post(
                f"/api/v1/help-centers/{hc_id}/tabs",
                json={"display_name": name, "knowledge_base_id": kb_id},
                headers=HEADERS,
            )
            ids.append(r.json()["id"])

        # Send only one of the two ids — should be rejected.
        resp = await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs/reorder",
            json={"tab_ids": [ids[0]]},
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert "reorder_set_mismatch" in resp.json()["message"]

    # ── slug check ──

    @pytest.mark.asyncio
    async def test_check_slug_unused_returns_available(
        self, client: AsyncClient
    ):
        hc_id = await _make_help_center(client)
        slug = _u("avail").lower()
        resp = await client.get(
            f"/api/v1/help-centers/{hc_id}/tabs/check-slug?slug={slug}",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["available"] is True

    @pytest.mark.asyncio
    async def test_check_slug_taken_returns_unavailable(
        self, client: AsyncClient
    ):
        hc_id = await _make_help_center(client)
        kb_id = await _make_kb(client)
        slug = _u("taken").lower()
        await client.post(
            f"/api/v1/help-centers/{hc_id}/tabs",
            json={"display_name": "X", "tab_slug": slug, "knowledge_base_id": kb_id},
            headers=HEADERS,
        )

        resp = await client.get(
            f"/api/v1/help-centers/{hc_id}/tabs/check-slug?slug={slug}",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["available"] is False
