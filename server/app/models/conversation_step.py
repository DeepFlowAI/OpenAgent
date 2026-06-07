"""
ConversationStep ORM model — atomic execution log entries within a conversation
"""
from datetime import datetime

from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


class ConversationStep(Base):
    __tablename__ = "conversation_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Primary text content (user text, assistant reply, etc.)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── LLM Call fields (populated when step_type = 'llm_call') ──
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    thinking_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    thinking_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_messages: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_tools: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Tool Call fields (populated when step_type = 'tool_call') ──
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_arguments: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tool_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── Relationships ──
    parent_step_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("conversation_steps.id", ondelete="SET NULL"), nullable=True
    )

    # ── Visitor feedback (populated on assistant_message steps) ──
    feedback_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # ── Sub-req 3: client-supplied idempotency key. Stable across all retries
    # of one logical user turn so the engine can detect duplicate submissions
    # and auto-resume instead of creating a second user_message + LLM round.
    # Only carried by step_type='user_message'; null on every other step.
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Common ──
    # `incomplete` (sub-req 2): partial llm_call step — see schemas/conversation_step.py.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_steps_conv_order", "conversation_id", "step_order"),
        Index("ix_steps_conv_round", "conversation_id", "round_number"),
        Index("ix_steps_type", "step_type"),
        Index("ix_steps_parent", "parent_step_id"),
        # Sub-req 3: prevent duplicate user_message rows within a single
        # conversation when the client retries with a stable client_message_id.
        Index(
            "ux_steps_conv_client_msg",
            "conversation_id", "client_message_id",
            unique=True,
            postgresql_where=text(
                "client_message_id IS NOT NULL AND step_type = 'user_message'"
            ),
        ),
        Index(
            "ix_steps_client_msg",
            "client_message_id",
            postgresql_where=text("client_message_id IS NOT NULL"),
        ),
    )
