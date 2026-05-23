"""
Agent message preprocessing rule router
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, require_scope
from app.schemas.agent_message_preprocessing_rule import (
    AgentMessagePreprocessingRuleCreate,
    AgentMessagePreprocessingRuleListResponse,
    AgentMessagePreprocessingRuleResponse,
    AgentMessagePreprocessingRuleUpdate,
)
from app.services.agent_message_preprocessing_rule_service import (
    AgentMessagePreprocessingRuleService,
)

router = APIRouter(
    prefix="/agents/{agent_id}/preprocessing-rules",
    tags=["AgentPreprocessingRules"],
)


@router.get("", response_model=AgentMessagePreprocessingRuleListResponse)
async def list_preprocessing_rules(
    agent_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """List all message preprocessing rules for an agent"""
    return await AgentMessagePreprocessingRuleService.list_rules(
        db, tenant_id, agent_id
    )


@router.post(
    "",
    response_model=AgentMessagePreprocessingRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_preprocessing_rule(
    agent_id: int,
    body: AgentMessagePreprocessingRuleCreate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Create a message preprocessing rule"""
    return await AgentMessagePreprocessingRuleService.create(
        db, tenant_id, agent_id, body
    )


@router.put("/{rule_id}", response_model=AgentMessagePreprocessingRuleResponse)
async def update_preprocessing_rule(
    agent_id: int,
    rule_id: int,
    body: AgentMessagePreprocessingRuleUpdate,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Update a message preprocessing rule"""
    return await AgentMessagePreprocessingRuleService.update(
        db, tenant_id, agent_id, rule_id, body
    )


@router.delete("/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_preprocessing_rule(
    agent_id: int,
    rule_id: int,
    tenant_id: str = Depends(require_scope("config")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message preprocessing rule"""
    await AgentMessagePreprocessingRuleService.delete(
        db, tenant_id, agent_id, rule_id
    )
    return {"message": "Deleted successfully"}
