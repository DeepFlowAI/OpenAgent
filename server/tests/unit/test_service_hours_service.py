"""
Unit tests for service hours service.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.repositories.service_hours_repository import ServiceHoursRepository
from app.schemas.service_hours import (
    ServiceHoursConfigPayload,
    ServiceHoursCreate,
    ServiceHoursUpdate,
)
from app.services.service_hours_service import ServiceHoursEvaluator, ServiceHoursService


def test_weekly_period_overlap_is_rejected():
    with pytest.raises(PydanticValidationError):
        ServiceHoursCreate(
            name="Default",
            weekly_periods=[
                {"day_of_week": 0, "start": "09:00", "end": "12:00"},
                {"day_of_week": 0, "start": "11:30", "end": "18:00"},
            ],
        )


def test_weekly_period_adjacent_ranges_are_allowed():
    payload = ServiceHoursCreate(
        name="Default",
        weekly_periods=[
            {"day_of_week": 0, "start": "09:00", "end": "12:00"},
            {"day_of_week": 0, "start": "12:00", "end": "18:00"},
        ],
    )

    assert len(payload.weekly_periods) == 2


def test_datetime_range_overlap_is_rejected():
    with pytest.raises(PydanticValidationError):
        ServiceHoursCreate(
            name="Default",
            holidays=[
                {
                    "name": "Holiday A",
                    "start_at": "2026-10-01T00:00:00+08:00",
                    "end_at": "2026-10-03T00:00:00+08:00",
                },
                {
                    "name": "Holiday B",
                    "start_at": "2026-10-02T00:00:00+08:00",
                    "end_at": "2026-10-04T00:00:00+08:00",
                },
            ],
        )


def test_evaluator_matches_weekly_period():
    config = ServiceHoursConfigPayload(
        weekly_periods=[
            {"day_of_week": 0, "start": "09:00", "end": "18:00"},
        ]
    )

    result = ServiceHoursEvaluator.evaluate(
        config,
        datetime.fromisoformat("2026-05-18T10:30:00+08:00"),
        "Asia/Shanghai",
    )

    assert result.is_in_service is True
    assert result.matched_rule == "weekly"


def test_evaluator_uses_left_closed_right_open_boundary():
    config = ServiceHoursConfigPayload(
        weekly_periods=[
            {"day_of_week": 0, "start": "09:00", "end": "18:00"},
        ]
    )

    result = ServiceHoursEvaluator.evaluate(
        config,
        datetime.fromisoformat("2026-05-18T18:00:00+08:00"),
        "Asia/Shanghai",
    )

    assert result.is_in_service is False
    assert result.matched_rule == "weekly"


def test_evaluator_holiday_blocks_weekly_period():
    config = ServiceHoursConfigPayload(
        weekly_periods=[
            {"day_of_week": 0, "start": "09:00", "end": "18:00"},
        ],
        holidays=[
            {
                "name": "Holiday",
                "start_at": "2026-05-18T00:00:00+08:00",
                "end_at": "2026-05-19T00:00:00+08:00",
            }
        ],
    )

    result = ServiceHoursEvaluator.evaluate(
        config,
        datetime.fromisoformat("2026-05-18T10:30:00+08:00"),
        "Asia/Shanghai",
    )

    assert result.is_in_service is False
    assert result.matched_rule == "holiday"


def test_evaluator_makeup_overrides_holiday_but_still_uses_weekly_period():
    config = ServiceHoursConfigPayload(
        weekly_periods=[
            {"day_of_week": 0, "start": "09:00", "end": "18:00"},
        ],
        holidays=[
            {
                "name": "Holiday",
                "start_at": "2026-05-18T00:00:00+08:00",
                "end_at": "2026-05-19T00:00:00+08:00",
            }
        ],
        makeup_days=[
            {
                "name": "Makeup",
                "start_at": "2026-05-18T09:00:00+08:00",
                "end_at": "2026-05-18T12:00:00+08:00",
            }
        ],
    )

    result = ServiceHoursEvaluator.evaluate(
        config,
        datetime.fromisoformat("2026-05-18T10:30:00+08:00"),
        "Asia/Shanghai",
    )

    assert result.is_in_service is True
    assert result.matched_rule == "makeup"


def test_evaluator_rejects_unknown_timezone():
    config = ServiceHoursConfigPayload()

    with pytest.raises(ValidationError):
        ServiceHoursEvaluator.evaluate(config, datetime(2026, 5, 18, 10, 30), "Never/Land")


def test_evaluator_uses_config_timezone_when_not_passed():
    config = ServiceHoursConfigPayload(
        timezone="Asia/Shanghai",
        weekly_periods=[
            {"day_of_week": 0, "start": "09:00", "end": "18:00"},
        ],
    )

    result = ServiceHoursEvaluator.evaluate(
        config,
        datetime.fromisoformat("2026-05-18T10:30:00+08:00"),
    )

    assert result.is_in_service is True
    assert result.matched_rule == "weekly"


@pytest.mark.asyncio
async def test_create_normalizes_name_before_lookup_and_persist(monkeypatch):
    calls = {}

    async def fake_get_by_tenant_and_name(db, tenant_id, name, exclude_id=None):
        calls["lookup"] = {
            "tenant_id": tenant_id,
            "name": name,
            "exclude_id": exclude_id,
        }
        return None

    async def fake_create(db, data):
        calls["create"] = data
        return SimpleNamespace(**data)

    monkeypatch.setattr(
        ServiceHoursRepository,
        "get_by_tenant_and_name",
        fake_get_by_tenant_and_name,
    )
    monkeypatch.setattr(ServiceHoursRepository, "create", fake_create)

    result = await ServiceHoursService.create(
        object(),
        "tenant-a",
        ServiceHoursCreate(name="  Default  "),
    )

    assert calls["lookup"]["name"] == "Default"
    assert calls["lookup"]["exclude_id"] is None
    assert calls["create"]["name"] == "Default"
    assert result.name == "Default"


@pytest.mark.asyncio
async def test_create_rejects_blank_name():
    with pytest.raises(ValidationError):
        await ServiceHoursService.create(
            object(),
            "tenant-a",
            ServiceHoursCreate(name="   "),
        )


@pytest.mark.asyncio
async def test_update_normalizes_name_before_lookup_and_persist(monkeypatch):
    item = SimpleNamespace(id=7, tenant_id="tenant-a", name="Default")
    calls = {}

    async def fake_get_by_id(db, service_hours_id):
        calls["get_id"] = service_hours_id
        return item

    async def fake_get_by_tenant_and_name(db, tenant_id, name, exclude_id=None):
        calls["lookup"] = {
            "tenant_id": tenant_id,
            "name": name,
            "exclude_id": exclude_id,
        }
        return None

    async def fake_update(db, target, data):
        calls["update"] = data
        for key, value in data.items():
            setattr(target, key, value)
        return target

    monkeypatch.setattr(ServiceHoursRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        ServiceHoursRepository,
        "get_by_tenant_and_name",
        fake_get_by_tenant_and_name,
    )
    monkeypatch.setattr(ServiceHoursRepository, "update", fake_update)

    result = await ServiceHoursService.update(
        object(),
        "tenant-a",
        7,
        ServiceHoursUpdate(name="  Support  "),
    )

    assert calls["get_id"] == 7
    assert calls["lookup"] == {
        "tenant_id": "tenant-a",
        "name": "Support",
        "exclude_id": 7,
    }
    assert calls["update"]["name"] == "Support"
    assert result.name == "Support"


@pytest.mark.asyncio
async def test_update_rejects_blank_name(monkeypatch):
    async def fake_get_by_id(db, service_hours_id):
        return SimpleNamespace(id=7, tenant_id="tenant-a", name="Default")

    monkeypatch.setattr(ServiceHoursRepository, "get_by_id", fake_get_by_id)

    with pytest.raises(ValidationError):
        await ServiceHoursService.update(
            object(),
            "tenant-a",
            7,
            ServiceHoursUpdate(name="   "),
        )
