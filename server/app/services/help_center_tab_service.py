"""
Help Center Tab service — business validation, slug generation, KB ownership
checks, and reorder atomicity.
"""
import re
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.help_center_tab import HelpCenterTab
from app.models.knowledge_base import KnowledgeBase
from app.repositories.help_center_repository import HelpCenterRepository
from app.repositories.help_center_tab_repository import HelpCenterTabRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.help_center_tab import (
    HelpCenterTabCreate,
    HelpCenterTabUpdate,
    TabFilterCondition,
)


_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def _generate_tab_slug() -> str:
    """Generate an opaque short code matching the slug regex.
    `secrets.token_urlsafe` returns base64-url; we lowercase and replace `_`
    with `-` then strip leading/trailing dashes."""
    raw = secrets.token_urlsafe(4).lower().replace("_", "-").strip("-")
    return f"t-{raw}"[:24]


async def _ensure_help_center(
    db: AsyncSession, tenant_id: str, help_center_id: int
):
    """Verify the Help Center exists and belongs to the caller's tenant."""
    hc = await HelpCenterRepository.get_by_id(db, help_center_id)
    if not hc or hc.tenant_id != tenant_id:
        raise NotFoundError("Help Center not found")
    return hc


async def _ensure_kb_for_tenant(
    db: AsyncSession, tenant_id: str, kb_id: int
) -> KnowledgeBase:
    kb = await KnowledgeBaseRepository.get_by_id(db, kb_id)
    if not kb or kb.tenant_id != tenant_id:
        raise ValidationError("knowledge_base_invalid")
    return kb


def _serialize(
    tab: HelpCenterTab, kb_name: str | None = None
) -> dict:
    return {
        "id": tab.id,
        "help_center_id": tab.help_center_id,
        "display_name": tab.display_name,
        "tab_slug": tab.tab_slug,
        "knowledge_base_id": tab.knowledge_base_id,
        "knowledge_base_name": kb_name,
        "fixed_filters": tab.fixed_filters or [],
        "sort_order": tab.sort_order,
        "created_at": tab.created_at,
        "updated_at": tab.updated_at,
    }


async def _attach_kb_names(
    db: AsyncSession, tabs: list[HelpCenterTab]
) -> list[dict]:
    """Bulk-resolve knowledge_base_name for a list of tabs in one query."""
    kb_ids = list({t.knowledge_base_id for t in tabs})
    name_by_id: dict[int, str] = {}
    if kb_ids:
        from sqlalchemy import select

        result = await db.execute(
            select(KnowledgeBase.id, KnowledgeBase.name).where(
                KnowledgeBase.id.in_(kb_ids)
            )
        )
        name_by_id = {row.id: row.name for row in result.all()}
    return [_serialize(t, name_by_id.get(t.knowledge_base_id)) for t in tabs]


class HelpCenterTabService:

    @staticmethod
    async def list_for_help_center(
        db: AsyncSession, tenant_id: str, help_center_id: int
    ) -> dict:
        await _ensure_help_center(db, tenant_id, help_center_id)
        tabs = await HelpCenterTabRepository.list_by_help_center(
            db, help_center_id
        )
        items = await _attach_kb_names(db, tabs)
        return {"items": items}

    @staticmethod
    async def create(
        db: AsyncSession,
        tenant_id: str,
        help_center_id: int,
        data: HelpCenterTabCreate,
    ) -> dict:
        await _ensure_help_center(db, tenant_id, help_center_id)
        kb = await _ensure_kb_for_tenant(db, tenant_id, data.knowledge_base_id)

        # Resolve slug: user-provided (validated for uniqueness) or auto-generated.
        slug = data.tab_slug
        if slug:
            existing = await HelpCenterTabRepository.get_by_help_center_and_slug(
                db, help_center_id, slug
            )
            if existing:
                raise ConflictError(f"Tab slug '{slug}' is already in use")
        else:
            for _ in range(3):
                candidate = _generate_tab_slug()
                if _SLUG_RE.match(candidate) and not (
                    await HelpCenterTabRepository.get_by_help_center_and_slug(
                        db, help_center_id, candidate
                    )
                ):
                    slug = candidate
                    break
            if not slug:
                # Extraordinarily unlikely — surface as 500 via generic error.
                raise ValidationError("Failed to allocate a unique tab slug")

        next_order = (
            await HelpCenterTabRepository.max_sort_order(db, help_center_id)
        ) + 1

        payload = {
            "help_center_id": help_center_id,
            "display_name": data.display_name,
            "tab_slug": slug,
            "knowledge_base_id": data.knowledge_base_id,
            "fixed_filters": [
                f.model_dump() for f in data.fixed_filters
            ],
            "sort_order": next_order,
        }
        tab = await HelpCenterTabRepository.create(db, payload)
        return _serialize(tab, kb.name)

    @staticmethod
    async def update(
        db: AsyncSession,
        tenant_id: str,
        help_center_id: int,
        tab_id: int,
        data: HelpCenterTabUpdate,
    ) -> dict:
        await _ensure_help_center(db, tenant_id, help_center_id)
        tab = await HelpCenterTabRepository.get_by_id(db, tab_id)
        if not tab or tab.help_center_id != help_center_id:
            raise NotFoundError("Tab not found")

        update_data: dict = {}

        if data.display_name is not None:
            update_data["display_name"] = data.display_name

        if data.tab_slug is not None and data.tab_slug != tab.tab_slug:
            existing = await HelpCenterTabRepository.get_by_help_center_and_slug(
                db, help_center_id, data.tab_slug, exclude_id=tab.id
            )
            if existing:
                raise ConflictError(
                    f"Tab slug '{data.tab_slug}' is already in use"
                )
            update_data["tab_slug"] = data.tab_slug

        kb_name: str | None = None
        if (
            data.knowledge_base_id is not None
            and data.knowledge_base_id != tab.knowledge_base_id
        ):
            kb = await _ensure_kb_for_tenant(db, tenant_id, data.knowledge_base_id)
            update_data["knowledge_base_id"] = data.knowledge_base_id
            kb_name = kb.name

        if data.fixed_filters is not None:
            update_data["fixed_filters"] = [
                f.model_dump() for f in data.fixed_filters
            ]

        updated = (
            await HelpCenterTabRepository.update(db, tab, update_data)
            if update_data
            else tab
        )

        # If kb_name wasn't fetched in this request (no kb change), look it up
        # so the response stays consistent for the client.
        if kb_name is None:
            kb = await KnowledgeBaseRepository.get_by_id(
                db, updated.knowledge_base_id
            )
            kb_name = kb.name if kb else None

        return _serialize(updated, kb_name)

    @staticmethod
    async def delete(
        db: AsyncSession,
        tenant_id: str,
        help_center_id: int,
        tab_id: int,
    ) -> None:
        await _ensure_help_center(db, tenant_id, help_center_id)
        tab = await HelpCenterTabRepository.get_by_id(db, tab_id)
        if not tab or tab.help_center_id != help_center_id:
            raise NotFoundError("Tab not found")
        await HelpCenterTabRepository.delete(db, tab)

    @staticmethod
    async def reorder(
        db: AsyncSession,
        tenant_id: str,
        help_center_id: int,
        tab_ids: list[int],
    ) -> dict:
        await _ensure_help_center(db, tenant_id, help_center_id)

        existing = await HelpCenterTabRepository.list_by_help_center(
            db, help_center_id
        )
        existing_ids = {t.id for t in existing}
        if set(tab_ids) != existing_ids or len(tab_ids) != len(existing_ids):
            raise ValidationError("reorder_set_mismatch")

        tabs = await HelpCenterTabRepository.reorder(
            db, help_center_id, tab_ids
        )
        items = await _attach_kb_names(db, tabs)
        return {"items": items}

    @staticmethod
    async def is_slug_available(
        db: AsyncSession,
        tenant_id: str,
        help_center_id: int,
        slug: str,
        exclude_id: int | None = None,
    ) -> bool:
        await _ensure_help_center(db, tenant_id, help_center_id)
        existing = await HelpCenterTabRepository.get_by_help_center_and_slug(
            db, help_center_id, slug, exclude_id=exclude_id
        )
        return existing is None

    # Helpers exported for tests.
    @staticmethod
    def generate_tab_slug() -> str:
        return _generate_tab_slug()


# Re-export the filter condition for convenience in tests.
__all__ = ["HelpCenterTabService", "TabFilterCondition"]
