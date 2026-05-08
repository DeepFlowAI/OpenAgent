"""
Help Center Pydantic schemas.
"""
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.schemas.base import TimestampSchema, PaginatedResponse


SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"


class HelpCenterCreate(BaseModel):
    """Payload for `POST /api/v1/help-centers`. Public-access fields are
    deliberately omitted — they are configured only on the detail page."""

    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)


class HelpCenterUpdate(BaseModel):
    """Payload for `PUT /api/v1/help-centers/{id}`. All fields are optional
    so the endpoint supports partial updates from the detail page."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    public_slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=48,
        pattern=SLUG_PATTERN,
    )
    site_name: str | None = Field(default=None, min_length=1, max_length=64)
    # Use HttpUrl for strict validation; serialized as str via mode="json".
    publisher_logo_url: HttpUrl | None = Field(default=None)


class HelpCenterResponse(TimestampSchema):
    """Returned to authenticated admin clients. `public_root_url` is computed
    server-side so the frontend never has to know `PUBLIC_DOCS_HOST` directly."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    name: str
    description: str | None = None
    public_slug: str | None = None
    site_name: str | None = None
    publisher_logo_url: str | None = None
    public_root_url: str | None = None


class HelpCenterListResponse(PaginatedResponse):
    items: list[HelpCenterResponse]


class SlugAvailabilityResponse(BaseModel):
    available: bool
