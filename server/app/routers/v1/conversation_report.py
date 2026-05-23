"""
Conversation Report router — aggregated overview and trend endpoints
for the per-agent 会话报表 page.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_scope
from app.schemas.conversation_report import (
    ConversationReportOverviewResponse,
    ConversationReportTrendResponse,
    TrendGranularity,
)
from app.services.conversation_report_service import ConversationReportService

router = APIRouter(
    prefix="/agents/{agent_id}/conversation-report",
    tags=["ConversationReport"],
)


@router.get("/overview", response_model=ConversationReportOverviewResponse)
async def get_overview(
    agent_id: int,
    started_at_from: datetime = Query(..., description="区间起，含 (UTC)"),
    started_at_to: datetime = Query(..., description="区间止，不含 (UTC)"),
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated overview metrics for the report page."""
    return await ConversationReportService.get_overview(
        db, tenant_id, agent_id, started_at_from, started_at_to
    )


@router.get("/trend", response_model=ConversationReportTrendResponse)
async def get_trend(
    agent_id: int,
    started_at_from: datetime = Query(..., description="区间起，含 (UTC)"),
    started_at_to: datetime = Query(..., description="区间止，不含 (UTC)"),
    granularity: TrendGranularity = Query(..., description="时间桶粒度"),
    tenant_id: str = Depends(require_scope("chat")),
    db: AsyncSession = Depends(get_db),
):
    """Trend buckets across the selected range at the given granularity."""
    return await ConversationReportService.get_trend(
        db, tenant_id, agent_id, started_at_from, started_at_to, granularity
    )
