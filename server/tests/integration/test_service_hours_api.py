"""
Integration tests for Service Hours API.
"""
import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import make_auth_header

TENANT_ID = "T_TEST_SERVICE_HOURS"
HEADERS = make_auth_header(TENANT_ID)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _payload(name: str) -> dict:
    return {
        "name": name,
        "description": "integration test",
        "weekly_periods": [
            {"day_of_week": 0, "start": "09:00", "end": "18:00"},
        ],
        "holidays": [],
        "makeup_days": [],
    }


class TestServiceHoursAPI:

    @pytest.mark.asyncio
    async def test_list_service_hours_returns_200(self, client: AsyncClient):
        resp = await client.get("/api/v1/service-hours", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_service_hours_rejects_invalid_page(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/service-hours?page=0",
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_service_hours_rejects_oversized_per_page(
        self, client: AsyncClient
    ):
        resp = await client.get(
            "/api/v1/service-hours?per_page=101",
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_service_hours_returns_201(self, client: AsyncClient):
        name = _unique("sh-create")
        resp = await client.post(
            "/api/v1/service-hours", json=_payload(name), headers=HEADERS
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == name
        assert data["weekly_periods"][0]["start"] == "09:00"

    @pytest.mark.asyncio
    async def test_create_service_hours_missing_name_returns_422(
        self, client: AsyncClient
    ):
        resp = await client.post(
            "/api/v1/service-hours",
            json={"weekly_periods": []},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_service_hours_returns_200(self, client: AsyncClient):
        name = _unique("sh-get")
        create_resp = await client.post(
            "/api/v1/service-hours", json=_payload(name), headers=HEADERS
        )
        service_hours_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/v1/service-hours/{service_hours_id}", headers=HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == name

    @pytest.mark.asyncio
    async def test_get_service_hours_not_found_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/service-hours/999999", headers=HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_service_hours_returns_200(self, client: AsyncClient):
        name = _unique("sh-update")
        create_resp = await client.post(
            "/api/v1/service-hours", json=_payload(name), headers=HEADERS
        )
        service_hours_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/service-hours/{service_hours_id}",
            json={"description": "updated desc"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "updated desc"

    @pytest.mark.asyncio
    async def test_delete_service_hours_returns_200(self, client: AsyncClient):
        name = _unique("sh-delete")
        create_resp = await client.post(
            "/api/v1/service-hours", json=_payload(name), headers=HEADERS
        )
        service_hours_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/service-hours/{service_hours_id}", headers=HEADERS
        )
        assert resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/service-hours/{service_hours_id}", headers=HEADERS
        )
        assert get_resp.status_code == 404
