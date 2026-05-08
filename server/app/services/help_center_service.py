"""
Help Center service — business validation + tenant isolation.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.help_center import HelpCenter
from app.repositories.help_center_repository import HelpCenterRepository
from app.schemas.help_center import HelpCenterCreate, HelpCenterUpdate


def build_public_root_url(public_slug: str | None) -> str | None:
    """Compose the visitor root URL from configured docs host. Returns None
    when the Help Center has not yet been published (slug missing)."""
    if not public_slug:
        return None
    host = settings.PUBLIC_DOCS_HOST.strip().rstrip("/")
    if not host:
        return None
    return f"https://{host}/hc/{public_slug}"


def serialize(item: HelpCenter) -> dict:
    """Convert ORM row to a dict suitable for HelpCenterResponse, injecting
    the computed `public_root_url`."""
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "name": item.name,
        "description": item.description,
        "public_slug": item.public_slug,
        "site_name": item.site_name,
        "publisher_logo_url": item.publisher_logo_url,
        "public_root_url": build_public_root_url(item.public_slug),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


class HelpCenterService:

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        page: int = 1,
        per_page: int = 10,
    ) -> dict:
        items, total = await HelpCenterRepository.get_paginated(
            db, tenant_id, page=page, per_page=per_page
        )
        pages = (total + per_page - 1) // per_page if per_page else 0
        return {
            "items": [serialize(it) for it in items],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_for_tenant(
        db: AsyncSession, tenant_id: str, help_center_id: int
    ) -> HelpCenter:
        """Fetch a Help Center scoped to the tenant. Returning 404 (not 403)
        when ownership mismatches avoids leaking existence to other tenants."""
        item = await HelpCenterRepository.get_by_id(db, help_center_id)
        if not item or item.tenant_id != tenant_id:
            raise NotFoundError("Help Center not found")
        return item

    @staticmethod
    async def create(
        db: AsyncSession, tenant_id: str, data: HelpCenterCreate
    ) -> dict:
        payload = data.model_dump()
        payload["tenant_id"] = tenant_id
        item = await HelpCenterRepository.create(db, payload)
        return serialize(item)

    @staticmethod
    async def update(
        db: AsyncSession,
        tenant_id: str,
        help_center_id: int,
        data: HelpCenterUpdate,
    ) -> dict:
        item = await HelpCenterService.get_for_tenant(
            db, tenant_id, help_center_id
        )

        update_data = data.model_dump(exclude_unset=True, mode="json")

        # Slug uniqueness check — only when slug actually changes to a
        # non-empty value. Empty string is normalized to None below.
        new_slug = update_data.get("public_slug")
        if "public_slug" in update_data and new_slug == "":
            update_data["public_slug"] = None
            new_slug = None

        if new_slug and new_slug != item.public_slug:
            # Slug is globally unique — slug collisions across tenants would
            # make the visitor URL /hc/{slug}/... ambiguous on the shared host.
            existing = await HelpCenterRepository.get_by_public_slug(
                db, new_slug, exclude_id=item.id
            )
            if existing:
                raise ConflictError(
                    f"Public slug '{new_slug}' is already in use"
                )

        # Coupling rule: once slug is set, site_name must be present.
        # Compute the post-update view of both fields and validate together.
        final_slug = (
            new_slug if "public_slug" in update_data else item.public_slug
        )
        final_site_name = (
            update_data.get("site_name")
            if "site_name" in update_data
            else item.site_name
        )
        if final_slug and not (final_site_name and final_site_name.strip()):
            raise ValidationError(
                "site_name is required when public_slug is set"
            )

        updated = await HelpCenterRepository.update(db, item, update_data)
        return serialize(updated)

    @staticmethod
    async def delete(
        db: AsyncSession, tenant_id: str, help_center_id: int
    ) -> None:
        item = await HelpCenterService.get_for_tenant(
            db, tenant_id, help_center_id
        )
        await HelpCenterRepository.delete(db, item)

    @staticmethod
    async def is_slug_available(
        db: AsyncSession,
        tenant_id: str,
        slug: str,
        exclude_id: int | None = None,
    ) -> bool:
        """Slug availability is checked GLOBALLY (uniqueness is platform-wide
        — see model docstring), but `exclude_id` is honoured ONLY when it
        belongs to the caller's tenant. A foreign id is silently dropped so
        admin clients cannot trick the API into reporting another tenant's
        slug as available."""
        if exclude_id is not None:
            owner = await HelpCenterRepository.get_by_id(db, exclude_id)
            if owner is None or owner.tenant_id != tenant_id:
                exclude_id = None

        existing = await HelpCenterRepository.get_by_public_slug(
            db, slug, exclude_id=exclude_id
        )
        return existing is None
