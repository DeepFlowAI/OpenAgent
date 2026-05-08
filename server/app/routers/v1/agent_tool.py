"""
AgentTool router — nested under /agents/{agent_id}/tools
"""
import time

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.deps import get_db, require_scope
from app.schemas.agent_tool import (
    AgentToolCreate,
    AgentToolUpdate,
    AgentToolToggle,
    AgentToolResponse,
    AgentToolListResponse,
    ToolExecuteRequest,
    ToolExecuteResponse,
)
from app.services.agent_tool_service import AgentToolService
from app.services.agent_service import AgentService

router = APIRouter(
    prefix="/agents/{agent_id}/tools",
    tags=["AgentTools"],
)


async def _verify_agent_ownership(
    agent_id: int, tenant_id: str, db: AsyncSession
) -> None:
    agent = await AgentService.get_by_id(db, agent_id)
    if agent.tenant_id != tenant_id:
        raise NotFoundError("Agent not found")


@router.get("", response_model=AgentToolListResponse)
async def list_agent_tools(
    agent_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """List all tools for an agent"""
    agent = await AgentService.get_by_id(db, agent_id)
    if agent.tenant_id != tenant_id:
        raise NotFoundError("Agent not found")
    return await AgentToolService.get_tools_by_agent(db, agent_id, agent.tenant_id)


@router.post("", response_model=AgentToolResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_tool(
    agent_id: int,
    body: AgentToolCreate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Add a tool to an agent"""
    agent = await AgentService.get_by_id(db, agent_id)
    if agent.tenant_id != tenant_id:
        raise NotFoundError("Agent not found")
    return await AgentToolService.create(db, agent_id, agent.tenant_id, body)


@router.get("/{tool_id}", response_model=AgentToolResponse)
async def get_agent_tool(
    agent_id: int,
    tool_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific agent tool"""
    await _verify_agent_ownership(agent_id, tenant_id, db)
    return await AgentToolService.get_by_id(db, tool_id, agent_id)


@router.put("/{tool_id}", response_model=AgentToolResponse)
async def update_agent_tool(
    agent_id: int,
    tool_id: int,
    body: AgentToolUpdate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Update tool configuration"""
    await _verify_agent_ownership(agent_id, tenant_id, db)
    return await AgentToolService.update(db, tool_id, agent_id, body)


@router.put("/{tool_id}/toggle", response_model=AgentToolResponse)
async def toggle_agent_tool(
    agent_id: int,
    tool_id: int,
    body: AgentToolToggle,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable a tool"""
    await _verify_agent_ownership(agent_id, tenant_id, db)
    return await AgentToolService.toggle(db, tool_id, agent_id, body)


@router.delete("/{tool_id}", status_code=status.HTTP_200_OK)
async def delete_agent_tool(
    agent_id: int,
    tool_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Remove a custom tool from an agent"""
    await _verify_agent_ownership(agent_id, tenant_id, db)
    await AgentToolService.delete(db, tool_id, agent_id)
    return {"message": "Tool removed successfully"}


@router.post("/{tool_id}/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    agent_id: int,
    tool_id: int,
    body: ToolExecuteRequest,
    conversation_id: int = 0,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Debug endpoint — execute a tool with given arguments and return the raw result."""
    from app.services.tool_executors import execute_tool as dispatch_tool, ToolContext

    agent = await AgentService.get_by_id(db, agent_id)
    if agent.tenant_id != tenant_id:
        raise NotFoundError("Agent not found")
    tool = await AgentToolService.get_by_id(db, tool_id, agent_id)

    tool_args = body.model_dump()

    ctx = ToolContext(
        db=db,
        conversation_id=conversation_id,
        tenant_id=agent.tenant_id,
        agent_id=agent_id,
    )

    start = int(time.time() * 1000)
    result = await dispatch_tool(
        tool_name=tool.name,
        tool_type=tool.tool_type,
        args=tool_args,
        config=tool.config or {},
        ctx=ctx,
    )
    duration = int(time.time() * 1000) - start

    return ToolExecuteResponse(
        tool_name=tool.name,
        tool_type=tool.tool_type,
        arguments=tool_args,
        result=result,
        duration_ms=duration,
    )
