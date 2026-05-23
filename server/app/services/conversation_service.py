"""
Conversation service — business logic for conversation management
"""
import csv
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.channel_repository import ChannelRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.conversation_step_repository import ConversationStepRepository
from app.schemas.conversation import (
    CONVERSATION_SOURCE_VALUES,
    ConversationCreate,
    normalize_channel_source,
    normalize_conversation_source,
)


EXPORT_COLUMNS = [
    "会话 ID",
    "会话内部 ID",
    "会话开始时间",
    "轮次",
    "用户消息 Step ID",
    "客户端消息 ID",
    "用户消息发送时间",
    "用户消息内容",
    "Agent 推理过程",
    "Agent 消息内容",
    "评价",
    "评价内容",
    "输入 Token",
    "输出 Token",
    "round_has_error",
]


def _value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _format_datetime(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _build_agent_reasoning_export(agent_steps: list[Any]) -> str:
    """Build export text: LLM thinking blocks and tool lines, in step order."""
    segments: list[str] = []
    for step in agent_steps:
        st = _value(step, "step_type")
        if st == "llm_call":
            text = (_value(step, "thinking_content") or "").strip()
            if text:
                segments.append(text)
        elif st == "tool_call":
            brief = (_value(step, "brief") or "").strip()
            tool_name = (_value(step, "tool_name") or "").strip()
            label = brief or tool_name or "unknown"
            segments.append(f"tool：{label}")
    return "\n\n---\n\n".join(segments)


def _format_feedback_rating(value: Any) -> str:
    if value == "like":
        return "赞"
    if value == "dislike":
        return "踩"
    return ""


def _parse_source_filter(source: str | None) -> list[str] | None:
    if source is None:
        return None
    raw_values = [part.strip() for part in source.split(",")]
    requested = [value for value in raw_values if value]
    if not requested:
        return None
    return [value for value in requested if value in CONVERSATION_SOURCE_VALUES]


def _parse_channel_id_filter(channel_id: str | None) -> list[int] | None:
    if channel_id is None:
        return None
    raw_values = [part.strip() for part in channel_id.split(",")]
    requested = [value for value in raw_values if value]
    if not requested:
        return None

    parsed: list[int] = []
    for value in requested:
        try:
            parsed_value = int(value)
        except ValueError:
            continue
        if parsed_value > 0 and parsed_value not in parsed:
            parsed.append(parsed_value)
    return parsed


class ConversationService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        *,
        page: int = 1,
        per_page: int = 10,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status: str | None = None,
        source: str | None = None,
        channel_id: str | None = None,
        channel_source: str | None = None,
        message_content: str | None = None,
        conversation_id: str | None = None,
        external_user_id: str | None = None,
        search: str | None = None,
    ) -> dict:
        source_filter = _parse_source_filter(source)
        channel_id_filter = _parse_channel_id_filter(channel_id)
        items, total = await ConversationRepository.get_paginated(
            db,
            tenant_id,
            agent_id,
            page=page,
            per_page=per_page,
            start_time=start_time,
            end_time=end_time,
            status=status,
            source=source_filter,
            channel_id=channel_id_filter,
            channel_source=channel_source.strip() if channel_source else None,
            message_content=message_content,
            conversation_id=conversation_id,
            external_user_id=external_user_id,
            search=search,
        )
        pages = (total + per_page - 1) // per_page
        return {
            "items": await ConversationService._serialize_conversations(
                db, tenant_id, items
            ),
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def export_messages_csv(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status: str | None = None,
        source: str | None = None,
        channel_id: str | None = None,
        channel_source: str | None = None,
        message_content: str | None = None,
        conversation_id: str | None = None,
        external_user_id: str | None = None,
        search: str | None = None,
    ) -> str:
        """Export all filtered conversations as CSV, one row per user round."""
        output = StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(EXPORT_COLUMNS)

        page = 1
        per_page = 500
        while True:
            source_filter = _parse_source_filter(source)
            channel_id_filter = _parse_channel_id_filter(channel_id)
            conversations, total = await ConversationRepository.get_paginated(
                db,
                tenant_id,
                agent_id,
                page=page,
                per_page=per_page,
                start_time=start_time,
                end_time=end_time,
                status=status,
                source=source_filter,
                channel_id=channel_id_filter,
                channel_source=channel_source.strip() if channel_source else None,
                message_content=message_content,
                conversation_id=conversation_id,
                external_user_id=external_user_id,
                search=search,
            )
            if not conversations:
                break

            for conversation in conversations:
                steps = await ConversationStepRepository.get_timeline(
                    db, conversation.id
                )
                writer.writerows(
                    ConversationService._build_export_rows(conversation, steps)
                )

            if page * per_page >= total:
                break
            page += 1

        return "\ufeff" + output.getvalue()

    @staticmethod
    def _build_export_rows(conversation: Any, steps: list[Any]) -> list[list[Any]]:
        rounds: dict[int, dict[str, Any]] = {}
        for step in steps:
            round_number = _value(step, "round_number")
            if round_number is None:
                continue
            group = rounds.setdefault(
                round_number,
                {"user_message": None, "agent_steps": []},
            )
            if _value(step, "step_type") == "user_message":
                group["user_message"] = step
            else:
                group["agent_steps"].append(step)

        rows: list[list[Any]] = []
        for round_number in sorted(rounds):
            group = rounds[round_number]
            user_message = group["user_message"]
            if user_message is None:
                continue

            agent_steps = sorted(
                group["agent_steps"],
                key=lambda step: _value(step, "step_order") or 0,
            )
            llm_steps = [
                step for step in agent_steps
                if _value(step, "step_type") == "llm_call"
            ]
            assistant_steps = [
                step for step in agent_steps
                if _value(step, "step_type") == "assistant_message"
            ]
            round_steps = [user_message, *agent_steps]
            thinking_content = _build_agent_reasoning_export(agent_steps)
            assistant_content = "\n\n".join(
                text
                for text in (
                    (_value(step, "content") or "").strip()
                    for step in assistant_steps
                )
                if text
            )
            feedback_rating = "；".join(
                label
                for label in (
                    _format_feedback_rating(_value(step, "feedback_rating"))
                    for step in assistant_steps
                )
                if label
            )
            feedback_comment = "；".join(
                comment
                for comment in (
                    (_value(step, "feedback_comment") or "").strip()
                    for step in assistant_steps
                )
                if comment
            )

            rows.append([
                conversation.external_id,
                conversation.id,
                _format_datetime(conversation.started_at),
                round_number,
                _value(user_message, "id"),
                _value(user_message, "client_message_id") or "",
                _format_datetime(_value(user_message, "created_at")),
                _value(user_message, "content") or "",
                thinking_content,
                assistant_content,
                feedback_rating,
                feedback_comment,
                sum(_value(step, "input_tokens") or 0 for step in llm_steps),
                sum(_value(step, "output_tokens") or 0 for step in llm_steps),
                "true" if any(
                    _value(step, "status") != "success"
                    for step in round_steps
                ) else "false",
            ])

        return rows

    @staticmethod
    async def get_by_id(db: AsyncSession, conversation_id: int) -> dict:
        item = await ConversationRepository.get_by_id(db, conversation_id)
        if not item:
            raise NotFoundError("Conversation not found")

        duration_seconds = None
        if item.started_at:
            end = item.ended_at or datetime.now(timezone.utc)
            if item.started_at.tzinfo is None:
                started = item.started_at.replace(tzinfo=timezone.utc)
            else:
                started = item.started_at
            duration_seconds = int((end - started).total_seconds())

        channel_names = await ChannelRepository.get_names_by_ids(
            db,
            item.tenant_id,
            [item.channel_id] if item.channel_id else [],
        )
        return {
            **ConversationService._serialize_conversation(item, channel_names),
            "duration_seconds": duration_seconds,
        }

    @staticmethod
    async def get_channel_options(
        db: AsyncSession, tenant_id: str, agent_id: int
    ) -> dict:
        items = await ChannelRepository.get_web_sdk_options_by_agent(
            db, tenant_id, agent_id
        )
        return {"items": items}

    @staticmethod
    async def create(db: AsyncSession, data: ConversationCreate):
        create_data = data.model_dump()
        create_data["source"] = normalize_conversation_source(
            create_data.get("source")
        )
        channel_names: dict[int, str] = {}
        channel_id = create_data.get("channel_id")
        tenant_id = create_data.get("tenant_id")
        if channel_id and tenant_id:
            channel_names = await ChannelRepository.get_names_by_ids(
                db, tenant_id, [channel_id]
            )
            if not channel_names:
                create_data.pop("channel_id", None)
        channel_source = normalize_channel_source(create_data.get("channel_source"))
        if channel_source:
            create_data["channel_source"] = channel_source
        else:
            create_data.pop("channel_source", None)
        item = await ConversationRepository.create(db, create_data)
        return ConversationService._serialize_conversation(item, channel_names)

    @staticmethod
    async def _serialize_conversations(
        db: AsyncSession, tenant_id: str, items: list[Any]
    ) -> list[dict]:
        channel_ids = sorted({
            item.channel_id for item in items if getattr(item, "channel_id", None)
        })
        channel_names = await ChannelRepository.get_names_by_ids(
            db, tenant_id, channel_ids
        )
        return [
            ConversationService._serialize_conversation(item, channel_names)
            for item in items
        ]

    @staticmethod
    def _serialize_conversation(item: Any, channel_names: dict[int, str]) -> dict:
        if isinstance(item, Mapping):
            payload = dict(item)
        else:
            payload = {c.key: getattr(item, c.key) for c in item.__table__.columns}
        channel_id = payload.get("channel_id")
        payload["channel_name"] = channel_names.get(channel_id) if channel_id else None
        return payload

    @staticmethod
    async def end_conversation(db: AsyncSession, conversation_id: int):
        item = await ConversationRepository.get_by_id(db, conversation_id)
        if not item:
            raise NotFoundError("Conversation not found")
        if item.status == "ended":
            return item
        return await ConversationRepository.update(
            db,
            item,
            {"status": "ended", "ended_at": datetime.now(timezone.utc)},
        )
