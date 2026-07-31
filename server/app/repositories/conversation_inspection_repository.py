"""Data access for human quality inspections."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.conversation_inspection import ConversationStepInspection, ConversationStepInspectionHistory


class ConversationInspectionRepository:
    @staticmethod
    async def get_by_step(db: AsyncSession, step_id: int) -> ConversationStepInspection | None:
        return (await db.execute(select(ConversationStepInspection).where(ConversationStepInspection.step_id == step_id))).scalar_one_or_none()

    @staticmethod
    async def list_by_conversation(db: AsyncSession, conversation_id: int) -> list[ConversationStepInspection]:
        return list((await db.execute(select(ConversationStepInspection).where(ConversationStepInspection.conversation_id == conversation_id))).scalars())

    @staticmethod
    async def save(db: AsyncSession, item: ConversationStepInspection | None, data: dict) -> ConversationStepInspection:
        if item is None:
            item = ConversationStepInspection(**data)
            db.add(item)
            await db.flush()
        else:
            for key, value in data.items():
                setattr(item, key, value)
            await db.flush()
        db.add(ConversationStepInspectionHistory(inspection_id=item.id, inspector_id=data.get("inspector_id"), tag=item.tag, issue_types=item.issue_types, issue_description=item.issue_description))
        await db.commit()
        await db.refresh(item)
        return item
