"""
API Key schemas
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import PaginatedResponse


# --- Legacy single-key schemas (backward compat) ---

class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    masked_key: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApiKeyFullResponse(BaseModel):
    key_value: str


# --- Multi-key management schemas ---

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(default=["chat"])
    description: str | None = None


class ApiKeyItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    masked_key: str
    scopes: list[str]
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApiKeyCreateResponse(ApiKeyItemResponse):
    """Returned on create/rotate — includes one-time full key."""
    key_value: str


class ApiKeyListResponse(PaginatedResponse):
    items: list[ApiKeyItemResponse]
