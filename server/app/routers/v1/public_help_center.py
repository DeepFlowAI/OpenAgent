"""
Public Help Center router (visitor-facing, no API key required).

Routes are nested under `/api/v1/public/help-centers/{slug}/...`. Resources
are resolved by `public_slug` so the internal numeric IDs and tenant_id are
never exposed.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db
from app.schemas.public_help_center import (
    PublicDocDetail,
    PublicDocList,
    PublicHelpCenterBundle,
)
from app.services.public_help_center_service import PublicHelpCenterService


router = APIRouter(
    prefix="/public/help-centers",
    tags=["Help Center (Public)"],
)


@router.get("/{slug}", response_model=PublicHelpCenterBundle)
async def get_bundle(slug: str, db: AsyncSession = Depends(get_db)):
    return await PublicHelpCenterService.get_bundle(db, slug)


@router.get(
    "/{slug}/tabs/{tab_slug}/docs",
    response_model=PublicDocList,
)
async def list_docs(
    slug: str,
    tab_slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await PublicHelpCenterService.list_docs(
        db, slug, tab_slug, page, per_page
    )


@router.get(
    "/{slug}/tabs/{tab_slug}/docs/{doc_path:path}",
    response_model=PublicDocDetail,
)
async def get_doc(
    slug: str,
    tab_slug: str,
    doc_path: str,
    db: AsyncSession = Depends(get_db),
):
    return await PublicHelpCenterService.get_doc(db, slug, tab_slug, doc_path)


@router.get("/{slug}/sitemap.xml")
async def get_sitemap(slug: str, db: AsyncSession = Depends(get_db)):
    xml = await PublicHelpCenterService.render_sitemap(db, slug)
    return Response(content=xml, media_type="application/xml")
