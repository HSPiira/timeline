"""Workflow API endpoints"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.tenant import Tenant
from src.infrastructure.persistence.models.workflow import Workflow
from src.infrastructure.persistence.repositories.workflow_repo import (
    WorkflowExecutionRepository, WorkflowRepository)
from src.presentation.api.dependencies import (get_current_tenant,
                                               get_current_user, get_db,
                                               get_db_transactional,
                                               require_permission)
from src.presentation.api.v1.schemas.token import TokenPayload
from src.presentation.api.v1.schemas.workflow import (
    WorkflowCreate, WorkflowExecutionResponse, WorkflowResponse,
    WorkflowUpdate)

router = APIRouter()


@router.post(
    "/",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("workflow", "create"))],
)
async def create_workflow(
    data: WorkflowCreate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
):
    """
    Create new workflow.

    Workflows automate actions when events occur.
    Example: Auto-escalate urgent issues, send notifications, create follow-up events.
    """
    repo = WorkflowRepository(db)

    workflow = Workflow(
        tenant_id=tenant.id,
        name=data.name,
        description=data.description,
        trigger_event_type=data.trigger_event_type,
        trigger_conditions=data.trigger_conditions,
        actions=data.actions,
        execution_order=data.execution_order,
        max_executions_per_day=data.max_executions_per_day,
        is_active=data.is_active,
        created_by=current_user.sub,
    )

    created = await repo.create(workflow)
    return WorkflowResponse.model_validate(created)


@router.get(
    "/",
    response_model=list[WorkflowResponse],
    dependencies=[Depends(require_permission("workflow", "read"))],
)
async def list_workflows(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    include_inactive: bool = Query(False),
):
    """List all workflows for tenant"""
    repo = WorkflowRepository(db)
    workflows = await repo.get_by_tenant(
        tenant_id=tenant.id, skip=skip, limit=limit, include_inactive=include_inactive
    )
    return [WorkflowResponse.model_validate(w) for w in workflows]


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    dependencies=[Depends(require_permission("workflow", "read"))],
)
async def get_workflow(
    workflow_id: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get workflow by ID"""
    repo = WorkflowRepository(db)
    workflow = await repo.get_by_id(workflow_id, tenant.id)

    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    return WorkflowResponse.model_validate(workflow)


@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    dependencies=[Depends(require_permission("workflow", "update"))],
)
async def update_workflow(
    workflow_id: str,
    data: WorkflowUpdate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
):
    """Update workflow"""
    repo = WorkflowRepository(db)
    workflow = await repo.get_by_id(workflow_id, tenant.id)

    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(workflow, field, value)

    updated = await repo.update(workflow)
    return WorkflowResponse.model_validate(updated)


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("workflow", "delete"))],
)
async def delete_workflow(
    workflow_id: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
):
    """Soft delete workflow"""
    repo = WorkflowRepository(db)
    deleted = await repo.soft_delete(workflow_id, tenant.id)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")


@router.get(
    "/{workflow_id}/executions",
    response_model=list[WorkflowExecutionResponse],
    dependencies=[Depends(require_permission("workflow", "read"))],
)
async def get_workflow_executions(
    workflow_id: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get execution history for workflow"""
    # Verify workflow exists and belongs to tenant
    workflow_repo = WorkflowRepository(db)
    workflow = await workflow_repo.get_by_id(workflow_id, tenant.id)

    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    # Get executions
    exec_repo = WorkflowExecutionRepository(db)
    executions = await exec_repo.get_by_workflow(
        workflow_id=workflow_id, tenant_id=tenant.id, skip=skip, limit=limit
    )

    return [WorkflowExecutionResponse.model_validate(e) for e in executions]


@router.get(
    "/executions/{execution_id}",
    response_model=WorkflowExecutionResponse,
    dependencies=[Depends(require_permission("workflow", "read"))],
)
async def get_execution(
    execution_id: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get workflow execution details"""
    repo = WorkflowExecutionRepository(db)
    execution = await repo.get_by_id(execution_id, tenant.id)

    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    return WorkflowExecutionResponse.model_validate(execution)
