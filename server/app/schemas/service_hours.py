"""
Service hours Pydantic schemas.
"""
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.base import PaginatedResponse, TimestampSchema

TIME_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"
DEFAULT_TIMEZONE = "Asia/Shanghai"


def time_to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _datetime_sort_key(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def validate_timezone(value: str) -> str:
    if not value:
        raise ValueError("Timezone is required")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unsupported timezone") from exc
    return value


class WeeklyServicePeriod(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start: str = Field(..., pattern=TIME_PATTERN)
    end: str = Field(..., pattern=TIME_PATTERN)

    @model_validator(mode="after")
    def validate_order(self) -> "WeeklyServicePeriod":
        if time_to_minutes(self.start) >= time_to_minutes(self.end):
            raise ValueError("End time must be after start time")
        return self


class ServiceHoursDateTimeRange(BaseModel):
    name: str | None = Field(None, max_length=32)
    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def validate_order(self) -> "ServiceHoursDateTimeRange":
        if _datetime_sort_key(self.start_at) >= _datetime_sort_key(self.end_at):
            raise ValueError("End time must be after start time")
        return self


def validate_weekly_periods(periods: list[WeeklyServicePeriod]) -> None:
    grouped: dict[int, list[WeeklyServicePeriod]] = {}
    for period in periods:
        grouped.setdefault(period.day_of_week, []).append(period)

    for items in grouped.values():
        sorted_items = sorted(items, key=lambda p: time_to_minutes(p.start))
        previous_end: int | None = None
        for item in sorted_items:
            start = time_to_minutes(item.start)
            end = time_to_minutes(item.end)
            if previous_end is not None and start < previous_end:
                raise ValueError("Time ranges cannot overlap")
            previous_end = end


def validate_datetime_ranges(ranges: list[ServiceHoursDateTimeRange]) -> None:
    sorted_ranges = sorted(ranges, key=lambda r: _datetime_sort_key(r.start_at))
    previous_end: datetime | None = None
    for item in sorted_ranges:
        start = _datetime_sort_key(item.start_at)
        end = _datetime_sort_key(item.end_at)
        if previous_end is not None and start < previous_end:
            raise ValueError("Time ranges cannot overlap")
        previous_end = end


class ServiceHoursBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=256)
    timezone: str = Field(DEFAULT_TIMEZONE, max_length=64)
    weekly_periods: list[WeeklyServicePeriod] = Field(default_factory=list)
    holidays: list[ServiceHoursDateTimeRange] = Field(default_factory=list)
    makeup_days: list[ServiceHoursDateTimeRange] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def validate_timezone_name(cls, value: str) -> str:
        return validate_timezone(value)

    @model_validator(mode="after")
    def validate_ranges(self) -> "ServiceHoursBase":
        validate_weekly_periods(self.weekly_periods)
        validate_datetime_ranges(self.holidays)
        validate_datetime_ranges(self.makeup_days)
        return self


class ServiceHoursCreate(ServiceHoursBase):
    pass


class ServiceHoursUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=256)
    timezone: str | None = Field(None, max_length=64)
    weekly_periods: list[WeeklyServicePeriod] | None = None
    holidays: list[ServiceHoursDateTimeRange] | None = None
    makeup_days: list[ServiceHoursDateTimeRange] | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return validate_timezone(value)

    @model_validator(mode="after")
    def validate_ranges(self) -> "ServiceHoursUpdate":
        if self.weekly_periods is not None:
            validate_weekly_periods(self.weekly_periods)
        if self.holidays is not None:
            validate_datetime_ranges(self.holidays)
        if self.makeup_days is not None:
            validate_datetime_ranges(self.makeup_days)
        return self


class ServiceHoursResponse(ServiceHoursBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str


class ServiceHoursListResponse(PaginatedResponse):
    items: list[ServiceHoursResponse]


class ServiceHoursConfigPayload(BaseModel):
    timezone: str = Field(DEFAULT_TIMEZONE, max_length=64)
    weekly_periods: list[WeeklyServicePeriod] = Field(default_factory=list)
    holidays: list[ServiceHoursDateTimeRange] = Field(default_factory=list)
    makeup_days: list[ServiceHoursDateTimeRange] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def validate_timezone_name(cls, value: str) -> str:
        return validate_timezone(value)

    @model_validator(mode="after")
    def validate_ranges(self) -> "ServiceHoursConfigPayload":
        validate_weekly_periods(self.weekly_periods)
        validate_datetime_ranges(self.holidays)
        validate_datetime_ranges(self.makeup_days)
        return self


class ServiceHoursEvaluation(BaseModel):
    is_in_service: bool
    matched_rule: Literal["makeup", "holiday", "weekly"]
