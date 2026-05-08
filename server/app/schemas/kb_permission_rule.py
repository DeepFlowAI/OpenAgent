"""
KbPermissionRule Pydantic schemas
"""
from pydantic import BaseModel, ConfigDict, Field

from app.enums import UserConditionOperator, ScopeOperator
from app.schemas.base import TimestampSchema


class UserCondition(BaseModel):
    field: str = Field(..., min_length=1, max_length=128, description="metadata key name")
    operator: UserConditionOperator
    value: str | list[str] | None = Field(
        None, description="Comparison value; null for is_empty/is_not_empty"
    )


class KbPermissionRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    enabled: bool = True
    user_conditions: list[UserCondition] = Field(..., min_length=1)
    scope_operator: ScopeOperator
    scope_labels: list[str] | None = Field(
        None, description="Required for equals/not_equals, null for contains_any/not_contains_any"
    )


class KbPermissionRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    enabled: bool | None = None
    user_conditions: list[UserCondition] | None = Field(None, min_length=1)
    scope_operator: ScopeOperator | None = None
    scope_labels: list[str] | None = None


class KbPermissionRuleResponse(TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    knowledge_base_id: int
    name: str
    enabled: bool
    user_conditions: list[dict]
    scope_operator: str
    scope_labels: list[str] | None = None
