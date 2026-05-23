"""
Service hours business logic and reusable evaluator.
"""
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.service_hours import ServiceHours
from app.repositories.service_hours_repository import ServiceHoursRepository
from app.schemas.service_hours import (
    DEFAULT_TIMEZONE,
    ServiceHoursConfigPayload,
    ServiceHoursCreate,
    ServiceHoursDateTimeRange,
    ServiceHoursEvaluation,
    ServiceHoursUpdate,
    WeeklyServicePeriod,
    time_to_minutes,
)


def _dump_schedule(data: ServiceHoursCreate | ServiceHoursUpdate) -> dict:
    return data.model_dump(exclude_unset=True, mode="json")


def _normalize_name(name: str | None) -> str:
    if name is None:
        raise ValidationError("Service hours name cannot be blank")
    normalized = name.strip()
    if not normalized:
        raise ValidationError("Service hours name cannot be blank")
    return normalized


def _resolve_zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError(f"Unsupported timezone: {timezone}") from exc


def _to_local(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


class ServiceHoursEvaluator:
    """Reusable in-process evaluator for service hours semantics."""

    @staticmethod
    def evaluate(
        config: ServiceHours | ServiceHoursConfigPayload | dict[str, Any],
        moment: datetime,
        timezone: str | None = None,
    ) -> ServiceHoursEvaluation:
        payload = ServiceHoursEvaluator._coerce_config(config)
        zone = _resolve_zone(timezone or payload.timezone)
        local_moment = _to_local(moment, zone)

        if ServiceHoursEvaluator._contains_any(
            payload.makeup_days, local_moment, zone
        ):
            return ServiceHoursEvaluation(
                is_in_service=ServiceHoursEvaluator._matches_weekly_period(
                    payload.weekly_periods, local_moment
                ),
                matched_rule="makeup",
            )

        if ServiceHoursEvaluator._contains_any(payload.holidays, local_moment, zone):
            return ServiceHoursEvaluation(is_in_service=False, matched_rule="holiday")

        return ServiceHoursEvaluation(
            is_in_service=ServiceHoursEvaluator._matches_weekly_period(
                payload.weekly_periods, local_moment
            ),
            matched_rule="weekly",
        )

    @staticmethod
    def _coerce_config(
        config: ServiceHours | ServiceHoursConfigPayload | dict[str, Any],
    ) -> ServiceHoursConfigPayload:
        if isinstance(config, ServiceHoursConfigPayload):
            return config
        if isinstance(config, ServiceHours):
            return ServiceHoursConfigPayload(
                weekly_periods=config.weekly_periods or [],
                holidays=config.holidays or [],
                makeup_days=config.makeup_days or [],
                timezone=config.timezone or DEFAULT_TIMEZONE,
            )
        return ServiceHoursConfigPayload.model_validate(config)

    @staticmethod
    def _contains_any(
        ranges: list[ServiceHoursDateTimeRange],
        local_moment: datetime,
        zone: ZoneInfo,
    ) -> bool:
        return any(
            _to_local(item.start_at, zone) <= local_moment < _to_local(item.end_at, zone)
            for item in ranges
        )

    @staticmethod
    def _matches_weekly_period(
        periods: list[WeeklyServicePeriod],
        local_moment: datetime,
    ) -> bool:
        day_of_week = local_moment.weekday()
        minute = local_moment.hour * 60 + local_moment.minute
        return any(
            period.day_of_week == day_of_week
            and time_to_minutes(period.start) <= minute < time_to_minutes(period.end)
            for period in periods
        )


class ServiceHoursService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        page: int = 1,
        per_page: int = 10,
    ) -> dict:
        items, total = await ServiceHoursRepository.get_paginated(
            db, tenant_id, page=page, per_page=per_page
        )
        pages = (total + per_page - 1) // per_page if per_page else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_for_tenant(
        db: AsyncSession, tenant_id: str, service_hours_id: int
    ) -> ServiceHours:
        item = await ServiceHoursRepository.get_by_id(db, service_hours_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Service hours not found")
        return item

    @staticmethod
    async def create(
        db: AsyncSession,
        tenant_id: str,
        data: ServiceHoursCreate,
    ) -> ServiceHours:
        name = _normalize_name(data.name)
        existing = await ServiceHoursRepository.get_by_tenant_and_name(
            db, tenant_id, name
        )
        if existing:
            raise ValidationError(
                f"Service hours with name '{name}' already exists"
            )
        payload = _dump_schedule(data)
        payload["name"] = name
        payload["tenant_id"] = tenant_id
        return await ServiceHoursRepository.create(db, payload)

    @staticmethod
    async def update(
        db: AsyncSession,
        tenant_id: str,
        service_hours_id: int,
        data: ServiceHoursUpdate,
    ) -> ServiceHours:
        item = await ServiceHoursService.get_for_tenant(
            db, tenant_id, service_hours_id
        )
        update_data = _dump_schedule(data)

        if "name" in update_data:
            next_name = _normalize_name(update_data["name"])
            update_data["name"] = next_name
            if next_name != item.name:
                existing = await ServiceHoursRepository.get_by_tenant_and_name(
                    db, tenant_id, next_name, exclude_id=item.id
                )
                if existing:
                    raise ValidationError(
                        f"Service hours with name '{next_name}' already exists"
                    )

        return await ServiceHoursRepository.update(db, item, update_data)

    @staticmethod
    async def delete(
        db: AsyncSession, tenant_id: str, service_hours_id: int
    ) -> None:
        item = await ServiceHoursService.get_for_tenant(
            db, tenant_id, service_hours_id
        )
        await ServiceHoursRepository.delete(db, item)

    @staticmethod
    async def evaluate_by_id(
        db: AsyncSession,
        tenant_id: str,
        service_hours_id: int,
        moment: datetime,
        timezone: str | None = None,
    ) -> ServiceHoursEvaluation:
        item = await ServiceHoursService.get_for_tenant(
            db, tenant_id, service_hours_id
        )
        return ServiceHoursEvaluator.evaluate(item, moment, timezone)
