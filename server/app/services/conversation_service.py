"""
Conversation service — business logic for conversation management
"""
import csv
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.conversation_step_repository import ConversationStepRepository
from app.schemas.conversation import ConversationCreate


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
        conversation_id: str | None = None,
        external_user_id: str | None = None,
        search: str | None = None,
    ) -> dict:
        items, total = await ConversationRepository.get_paginated(
            db,
            tenant_id,
            agent_id,
            page=page,
            per_page=per_page,
            start_time=start_time,
            end_time=end_time,
            status=status,
            source=source,
            conversation_id=conversation_id,
            external_user_id=external_user_id,
            search=search,
        )
        pages = (total + per_page - 1) // per_page
        return {
            "items": items,
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
            conversations, total = await ConversationRepository.get_paginated(
                db,
                tenant_id,
                agent_id,
                page=page,
                per_page=per_page,
                start_time=start_time,
                end_time=end_time,
                status=status,
                source=source,
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

        return {
            **{c.key: getattr(item, c.key) for c in item.__table__.columns},
            "duration_seconds": duration_seconds,
        }

    @staticmethod
    async def create(db: AsyncSession, data: ConversationCreate):
        create_data = data.model_dump()
        return await ConversationRepository.create(db, create_data)

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
