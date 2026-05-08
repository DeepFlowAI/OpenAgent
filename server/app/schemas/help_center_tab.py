"""
Help Center Tab Pydantic schemas.

Mirrors the `[{field, op, value}]` shape used by `agent_tools.config.fixed_filters`
so visitor-side rendering can reuse the existing meta-filter pipeline.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TAB_SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"

_FilterOp = Literal["eq", "ne", "gt", "ge", "lt", "le", "in"]


class TabFilterCondition(BaseModel):
    """One row of the doc-meta fixed filter. Matches the OData-aligned shape
    used throughout the project (see services/tool_executors/search_executor)."""

    field: str = Field(..., min_length=1, max_length=128)
    op: _FilterOp
    value: Any = None  # Scalar, or list when op == "in"

    @model_validator(mode="after")
    def _check_value(self) -> "TabFilterCondition":
        if self.op == "in" and not isinstance(self.value, list):
            raise ValueError("op=in requires value to be a list")
        if self.op != "in" and isinstance(self.value, list):
            raise ValueError("Only op=in accepts a list value")
        return self


class HelpCenterTabBase(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=32)
    tab_slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=48,
        pattern=TAB_SLUG_PATTERN,
    )
    knowledge_base_id: int
    fixed_filters: list[TabFilterCondition] = Field(default_factory=list)


class HelpCenterTabCreate(HelpCenterTabBase):
    pass


class HelpCenterTabUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=32)
    tab_slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=48,
        pattern=TAB_SLUG_PATTERN,
    )
    knowledge_base_id: int | None = None
    fixed_filters: list[TabFilterCondition] | None = None


class HelpCenterTabResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    help_center_id: int
    display_name: str
    tab_slug: str | None
    knowledge_base_id: int
    knowledge_base_name: str | None = None
    fixed_filters: list[TabFilterCondition]
    sort_order: int
    created_at: Any | None = None
    updated_at: Any | None = None


class HelpCenterTabListResponse(BaseModel):
    items: list[HelpCenterTabResponse]


class TabReorderRequest(BaseModel):
    tab_ids: list[int] = Field(..., min_length=1)


class TabSlugAvailabilityResponse(BaseModel):
    available: bool
