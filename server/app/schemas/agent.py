"""
Agent Pydantic schemas
"""
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.base import TimestampSchema, PaginatedResponse


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=256)


class AgentCreate(AgentBase):
    tenant_id: str | None = Field(None, max_length=32)


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = Field(None, max_length=256)


class AgentStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(active|inactive)$")


class ModelConfig(BaseModel):
    model_name: str = "gpt-4o"
    first_round_thinking: bool = False
    subsequent_rounds_thinking: bool = False
    temperature: float = Field(default=0.01, ge=0, le=2)
    top_p: float = Field(default=0.85, ge=0, le=1)
    max_tokens: int = Field(default=4096, gt=0)

    @model_validator(mode="before")
    @classmethod
    def _migrate_thinking_mode(cls, data: Any) -> Any:
        """Backward compat: map legacy `thinking_mode` to the new split fields."""
        if not isinstance(data, dict):
            return data
        legacy = data.pop("thinking_mode", None)
        if legacy is not None:
            if "first_round_thinking" not in data:
                data["first_round_thinking"] = bool(legacy)
            if "subsequent_rounds_thinking" not in data:
                data["subsequent_rounds_thinking"] = bool(legacy)
        return data


class ContextConfig(BaseModel):
    max_rounds: int = Field(default=0, ge=0)
    history_tool_rounds: int = Field(default=0, ge=0, le=5)
    recent_full_tool_responses: int = Field(default=1, ge=1, le=5)


class PreRecallConfig(BaseModel):
    enabled: bool = False
    tool_id: int | None = None


class WelcomeMarkdownBlock(BaseModel):
    type: Literal["markdown"] = "markdown"
    content: str = Field(default="", max_length=20000)


class WelcomeEmbedBlock(BaseModel):
    type: Literal["embed"] = "embed"
    embed_code: str = Field(default="", max_length=50000)
    height: int = Field(default=360, gt=0)


WelcomeMessageBlock = Annotated[
    WelcomeMarkdownBlock | WelcomeEmbedBlock,
    Field(discriminator="type"),
]


class WelcomeMessageConfig(BaseModel):
    enabled: bool = False
    blocks: list[WelcomeMessageBlock] = Field(default_factory=list)


class AIDisclaimerConfig(BaseModel):
    enabled: bool = False
    content: str = Field(default="本内容由AI生成，仅供参考", max_length=200)

    @model_validator(mode="after")
    def _validate_enabled_content(self) -> "AIDisclaimerConfig":
        if self.enabled and not self.content.strip():
            raise ValueError("AI disclaimer content is required when enabled")
        return self


class ToolCallLimitReplyConfig(BaseModel):
    enabled: bool = True
    content: str = Field(
        default="抱歉，本轮回复已达到工具调用上限，暂时无法继续处理。请简化问题、缩小查询范围或稍后重试。",
        max_length=300,
        description="Markdown source shown to users when a turn reaches the tool-call limit.",
    )

    @model_validator(mode="after")
    def _validate_enabled_content(self) -> "ToolCallLimitReplyConfig":
        if self.enabled and not self.content.strip():
            raise ValueError("Tool-call limit reply content is required when enabled")
        return self


class ConversationSettingsConfig(BaseModel):
    welcome_message: WelcomeMessageConfig = Field(default_factory=WelcomeMessageConfig)
    ai_disclaimer: AIDisclaimerConfig = Field(default_factory=AIDisclaimerConfig)
    tool_call_limit_reply: ToolCallLimitReplyConfig = Field(
        default_factory=ToolCallLimitReplyConfig
    )


class EngineConfig(BaseModel):
    system_prompt: str = Field(default="", max_length=10000)
    model: ModelConfig = Field(default_factory=ModelConfig)
    selected_tool_ids: list[int] = Field(default_factory=list)
    context: ContextConfig = Field(default_factory=ContextConfig)
    pre_recall: PreRecallConfig = Field(default_factory=PreRecallConfig)
    conversation_settings: ConversationSettingsConfig = Field(
        default_factory=ConversationSettingsConfig
    )


class EngineConfigUpdate(BaseModel):
    """Partial top-level update.

    If a ``conversation_settings`` section is provided, that section must be
    submitted as a complete object so nested fields are replaced deliberately.
    """

    @model_validator(mode="before")
    @classmethod
    def _validate_complete_conversation_settings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "conversation_settings" not in data or data["conversation_settings"] is None:
            return data

        settings = data["conversation_settings"]
        if not isinstance(settings, dict):
            return data

        allowed_sections = {
            "welcome_message",
            "ai_disclaimer",
            "tool_call_limit_reply",
        }
        submitted_sections = allowed_sections.intersection(settings.keys())
        if not submitted_sections:
            raise ValueError(
                "conversation_settings must include at least one supported section"
            )

        welcome = settings.get("welcome_message")
        if "welcome_message" in submitted_sections and (
            not isinstance(welcome, dict)
            or not {"enabled", "blocks"}.issubset(welcome.keys())
        ):
            raise ValueError(
                "conversation_settings.welcome_message must include enabled and blocks"
            )

        disclaimer = settings.get("ai_disclaimer")
        if "ai_disclaimer" in submitted_sections and (
            not isinstance(disclaimer, dict)
            or not {"enabled", "content"}.issubset(disclaimer.keys())
        ):
            raise ValueError(
                "conversation_settings.ai_disclaimer must include enabled and content"
            )

        tool_limit = settings.get("tool_call_limit_reply")
        if "tool_call_limit_reply" in submitted_sections and (
            not isinstance(tool_limit, dict)
            or not {"enabled", "content"}.issubset(tool_limit.keys())
        ):
            raise ValueError(
                "conversation_settings.tool_call_limit_reply must include enabled and content"
            )

        return data

    system_prompt: str | None = Field(None, max_length=10000)
    model: ModelConfig | None = None
    selected_tool_ids: list[int] | None = None
    context: ContextConfig | None = None
    pre_recall: PreRecallConfig | None = None
    conversation_settings: ConversationSettingsConfig | None = None


class AgentResponse(AgentBase, TimestampSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    status: str = "active"
    engine_config: dict[str, Any] = Field(default_factory=dict)


class AgentListResponse(PaginatedResponse):
    items: list[AgentResponse]
