"""Business logic for the quality-workbench queue and labels."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.conversation_inspection_repository import ConversationInspectionRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.conversation_step_repository import ConversationStepRepository
from app.schemas.conversation_inspection import InspectionSave
from app.services.conversation_service import ConversationService


class ConversationInspectionService:
    @staticmethod
    def _summary(assistant_count: int, inspections: list) -> tuple[str, str | None]:
        count = len(inspections)
        if not count: return "pending", None
        if count < assistant_count: return "in_progress", None
        tags = {item.tag for item in inspections}
        return "completed", "bad" if "bad" in tags else "pass" if "pass" in tags else "good"

    @staticmethod
    async def get_queue(db: AsyncSession, tenant_id: str, agent_id: int, **filters: object) -> dict:
        requested_status = filters.pop("inspection_status", None)
        requested_tag = filters.pop("inspection_tag", None)
        listed = await ConversationService.get_paginated(db, tenant_id, agent_id, page=1, per_page=1000, **filters)
        items = []
        for conversation in listed["items"]:
            steps = await ConversationStepRepository.get_timeline(db, conversation["id"])
            assistants = [step for step in steps if step["step_type"] == "assistant_message" and step["status"] == "success"]
            inspections = await ConversationInspectionRepository.list_by_conversation(db, conversation["id"])
            status, tag = ConversationInspectionService._summary(len(assistants), inspections)
            if requested_status == "unfinished" and status == "completed": continue
            if requested_status and requested_status not in {"unfinished", status}: continue
            if requested_tag and tag != requested_tag: continue
            items.append({**conversation, "inspection_status": status, "inspection_tag": tag, "assistant_reply_count": len(assistants), "inspected_count": len(inspections)})
        return {"items": items, "total": len(items)}

    @staticmethod
    async def save(db: AsyncSession, *, tenant_id: str, agent_id: int, conversation_id: int, step_id: int, inspector_id: int | None, data: InspectionSave) -> dict:
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id or conversation.agent_id != agent_id:
            raise NotFoundError("Conversation not found")
        step = await ConversationStepRepository.get_by_id(db, step_id)
        if not step or step.conversation_id != conversation_id or step.step_type != "assistant_message":
            raise NotFoundError("Assistant message not found")
        if data.tag != "bad" and (data.issue_types or data.issue_description):
            raise ValidationError("Bad details require the bad tag")
        item = await ConversationInspectionRepository.save(db, await ConversationInspectionRepository.get_by_step(db, step_id), {"tenant_id": tenant_id, "conversation_id": conversation_id, "step_id": step_id, "inspector_id": inspector_id, **data.model_dump()})
        return {"step_id": step_id, "tag": item.tag, "issue_types": item.issue_types, "issue_description": item.issue_description, "updated_at": item.updated_at}
