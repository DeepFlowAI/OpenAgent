"""
Agent router
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.deps import get_db, require_scope
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentStatusUpdate,
    AgentResponse,
    AgentListResponse,
    EngineConfigUpdate,
)
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=AgentListResponse)
async def list_agents(
    tenant_id: str = Depends(require_scope("config")),
    status_filter: str = "active",
    page: int = 1,
    per_page: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """List agents for a tenant, filtered by status"""
    return await AgentService.get_paginated(
        db, tenant_id, status=status_filter, page=page, per_page=per_page
    )


@router.post(
    "", response_model=AgentResponse, status_code=status.HTTP_201_CREATED
)
async def create_agent(
    body: AgentCreate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent"""
    body.tenant_id = tenant_id
    return await AgentService.create(db, body)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Get agent by ID"""
    agent = await AgentService.get_by_id(db, agent_id)
    if agent.tenant_id != tenant_id:
        raise NotFoundError("Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: int,
    body: AgentUpdate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Update agent basic info"""
    agent = await AgentService.get_by_id(db, agent_id)
    if agent.tenant_id != tenant_id:
        raise NotFoundError("Agent not found")
    return await AgentService.update(db, agent_id, body)


@router.put("/{agent_id}/status", response_model=AgentResponse)
async def update_agent_status(
    agent_id: int,
    body: AgentStatusUpdate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable an agent"""
    agent = await AgentService.get_by_id(db, agent_id)
    if agent.tenant_id != tenant_id:
        raise NotFoundError("Agent not found")
    return await AgentService.update_status(db, agent_id, body)


@router.put("/{agent_id}/engine-config", response_model=AgentResponse)
async def update_engine_config(
    agent_id: int,
    body: EngineConfigUpdate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Update agent engine configuration"""
    agent = await AgentService.get_by_id(db, agent_id)
    if agent.tenant_id != tenant_id:
        raise NotFoundError("Agent not found")
    return await AgentService.update_engine_config(db, agent_id, body)
