"""Tenant account request and response schemas."""

import re
from datetime import datetime
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AccountRole = Literal["admin", "quality_inspector"]


class AccountPageSize(IntEnum):
    DEFAULT = 20
    MEDIUM = 50
    LARGE = 100


USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{4,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,32}$")


def normalize_username(value: str) -> str:
    """Validate and normalize a user-facing username."""
    stripped = value.strip()
    if not USERNAME_RE.fullmatch(stripped) or "@" in stripped:
        raise ValueError(
            "Username must be 4–32 characters using letters, numbers, dots, "
            "underscores, or hyphens"
        )
    return stripped


def normalize_email(value: str) -> str:
    """Validate and normalize a user-facing email."""
    stripped = value.strip()
    if len(stripped) > 128 or not EMAIL_RE.fullmatch(stripped):
        raise ValueError("Enter a valid email address")
    return stripped


def validate_password(value: str) -> str:
    """Validate the account password policy."""
    if not PASSWORD_RE.fullmatch(value):
        raise ValueError(
            "Password must be 8–32 characters and include uppercase, "
            "lowercase, and a number"
        )
    return value


class AccountCreate(BaseModel):
    username: str
    email: str
    role: AccountRole = "quality_inspector"
    password: str
    agent_ids: list[int] = Field(default_factory=list)
    knowledge_base_ids: list[int] = Field(default_factory=list)

    _username = field_validator("username")(normalize_username)
    _email = field_validator("email")(normalize_email)
    _password = field_validator("password")(validate_password)

    @model_validator(mode="after")
    def normalize_access(self) -> "AccountCreate":
        self.agent_ids = sorted(set(self.agent_ids))
        self.knowledge_base_ids = sorted(set(self.knowledge_base_ids))
        return self


class AccountUpdate(BaseModel):
    username: str
    email: str
    role: AccountRole
    password: str | None = None
    agent_ids: list[int] = Field(default_factory=list)
    knowledge_base_ids: list[int] = Field(default_factory=list)

    _username = field_validator("username")(normalize_username)
    _email = field_validator("email")(normalize_email)

    @field_validator("password")
    @classmethod
    def validate_optional_password(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        return validate_password(value)

    @model_validator(mode="after")
    def normalize_access(self) -> "AccountUpdate":
        self.agent_ids = sorted(set(self.agent_ids))
        self.knowledge_base_ids = sorted(set(self.knowledge_base_ids))
        return self


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: AccountRole
    agent_ids: list[int] = Field(default_factory=list)
    agent_names: list[str] = Field(default_factory=list)
    knowledge_base_ids: list[int] = Field(default_factory=list)
    knowledge_base_names: list[str] = Field(default_factory=list)
    is_current: bool = False
    is_last_admin: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    total: int
    page: int
    per_page: int
    pages: int


class AccountResourceOption(BaseModel):
    id: int
    name: str
    status: str | None = None


class AccountResourceOptionsResponse(BaseModel):
    agents: list[AccountResourceOption]
    knowledge_bases: list[AccountResourceOption]


class AccountDeleteResponse(BaseModel):
    message: str
