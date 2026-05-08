"""
KbPermissionRule service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.enums import ScopeOperator
from app.repositories.kb_permission_rule_repository import KbPermissionRuleRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.kb_permission_rule import KbPermissionRuleCreate, KbPermissionRuleUpdate


class KbPermissionRuleService:

    @staticmethod
    async def _ensure_kb_exists(db: AsyncSession, kb_id: int) -> None:
        kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
        if not kb or kb.status == "deleted":
            raise NotFoundError("Knowledge base not found")

    @staticmethod
    def _validate_scope(scope_operator: str, scope_labels: list[str] | None) -> None:
        if scope_operator in (ScopeOperator.EQUALS, ScopeOperator.NOT_EQUALS):
            if not scope_labels:
                raise ValidationError(
                    f"scope_labels is required when scope_operator is '{scope_operator}'"
                )
        elif scope_operator in (ScopeOperator.CONTAINS_ANY, ScopeOperator.NOT_CONTAINS_ANY):
            if scope_labels:
                raise ValidationError(
                    f"scope_labels must be null when scope_operator is '{scope_operator}'"
                )

    @staticmethod
    async def list_rules(
        db: AsyncSession, tenant_id: str, kb_id: int
    ) -> list:
        await KbPermissionRuleService._ensure_kb_exists(db, kb_id)
        return await KbPermissionRuleRepository.list_by_kb(db, tenant_id, kb_id)

    @staticmethod
    async def get_by_id(
        db: AsyncSession, tenant_id: str, kb_id: int, rule_id: int
    ):
        await KbPermissionRuleService._ensure_kb_exists(db, kb_id)
        item = await KbPermissionRuleRepository.get_by_id(db, rule_id)
        if not item or item.knowledge_base_id != kb_id or item.tenant_id != tenant_id:
            raise NotFoundError("Permission rule not found")
        return item

    @staticmethod
    async def create(
        db: AsyncSession, tenant_id: str, kb_id: int, data: KbPermissionRuleCreate
    ):
        await KbPermissionRuleService._ensure_kb_exists(db, kb_id)
        KbPermissionRuleService._validate_scope(data.scope_operator, data.scope_labels)

        create_data = data.model_dump()
        # Serialize user_conditions to list of dicts
        create_data["user_conditions"] = [
            uc.model_dump() for uc in data.user_conditions
        ]
        create_data["tenant_id"] = tenant_id
        create_data["knowledge_base_id"] = kb_id
        return await KbPermissionRuleRepository.create(db, create_data)

    @staticmethod
    async def update(
        db: AsyncSession, tenant_id: str, kb_id: int, rule_id: int,
        data: KbPermissionRuleUpdate,
    ):
        item = await KbPermissionRuleService.get_by_id(db, tenant_id, kb_id, rule_id)

        update_data = data.model_dump(exclude_unset=True)

        # Resolve final scope values for validation
        final_operator = update_data.get("scope_operator", item.scope_operator)
        final_labels = update_data.get("scope_labels", item.scope_labels)
        KbPermissionRuleService._validate_scope(final_operator, final_labels)

        if "user_conditions" in update_data and update_data["user_conditions"] is not None:
            update_data["user_conditions"] = [
                uc.model_dump() if hasattr(uc, "model_dump") else uc
                for uc in data.user_conditions
            ]

        return await KbPermissionRuleRepository.update(db, item, update_data)

    @staticmethod
    async def delete(
        db: AsyncSession, tenant_id: str, kb_id: int, rule_id: int
    ) -> None:
        item = await KbPermissionRuleService.get_by_id(db, tenant_id, kb_id, rule_id)
        await KbPermissionRuleRepository.delete(db, item)

    @staticmethod
    async def toggle(
        db: AsyncSession, tenant_id: str, kb_id: int, rule_id: int
    ):
        item = await KbPermissionRuleService.get_by_id(db, tenant_id, kb_id, rule_id)
        return await KbPermissionRuleRepository.update(
            db, item, {"enabled": not item.enabled}
        )
