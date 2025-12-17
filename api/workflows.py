"""Workflow API endpoints"""
from typing import Annotated, List
from fastapi import APIRouter, Depends, status, HTTPException, Query
from models.tenant import Tenant
from models.workflow import Workflow
from api.deps import (
    get_current_tenant,
    require_permission,
    get_db_transactional,
    get_db
)
from schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowExecutionResponse
)
from repositories.workflow_repo import WorkflowRepository, WorkflowExecutionRepository
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


@router.post(
    "/",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("workflow", "create"))]
)
async def create_workflow(
    data: WorkflowCreate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)]
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
        created_by=None  # TODO: Get from user context
    )

    created = await repo.create(workflow)
    return WorkflowResponse.model_validate(created)


@router.get(
    "/",
    response_model=List[WorkflowResponse],
    dependencies=[Depends(require_permission("workflow", "read"))]
)
async def list_workflows(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    include_inactive: bool = Query(False)
):
    """List all workflows for tenant"""
    repo = WorkflowRepository(db)
    workflows = await repo.get_by_tenant(
        tenant_id=tenant.id,
        skip=skip,
        limit=limit,
        include_inactive=include_inactive
    )
    return [WorkflowResponse.model_validate(w) for w in workflows]


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    dependencies=[Depends(require_permission("workflow", "read"))]
)
async def get_workflow(
    workflow_id: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get workflow by ID"""
    repo = WorkflowRepository(db)
    workflow = await repo.get_by_id(workflow_id, tenant.id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    return WorkflowResponse.model_validate(workflow)


@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    dependencies=[Depends(require_permission("workflow", "update"))]
)
async def update_workflow(
    workflow_id: str,
    data: WorkflowUpdate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)]
):
    """Update workflow"""
    repo = WorkflowRepository(db)
    workflow = await repo.get_by_id(workflow_id, tenant.id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    # Update fields
    if data.name is not None:
        workflow.name = data.name
    if data.description is not None:
        workflow.description = data.description
    if data.trigger_conditions is not None:
        workflow.trigger_conditions = data.trigger_conditions
    if data.actions is not None:
        workflow.actions = data.actions
    if data.execution_order is not None:
        workflow.execution_order = data.execution_order
    if data.max_executions_per_day is not None:
        workflow.max_executions_per_day = data.max_executions_per_day
    if data.is_active is not None:
        workflow.is_active = data.is_active

    updated = await repo.update(workflow)
    return WorkflowResponse.model_validate(updated)


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("workflow", "delete"))]
)
async def delete_workflow(
    workflow_id: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)]
):
    """Soft delete workflow"""
    repo = WorkflowRepository(db)
    deleted = await repo.soft_delete(workflow_id, tenant.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )


@router.get(
    "/{workflow_id}/executions",
    response_model=List[WorkflowExecutionResponse],
    dependencies=[Depends(require_permission("workflow", "read"))]
)
async def get_workflow_executions(
    workflow_id: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get execution history for workflow"""
    # Verify workflow exists and belongs to tenant
    workflow_repo = WorkflowRepository(db)
    workflow = await workflow_repo.get_by_id(workflow_id, tenant.id)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    # Get executions
    exec_repo = WorkflowExecutionRepository(db)
    executions = await exec_repo.get_by_workflow(
        workflow_id=workflow_id,
        tenant_id=tenant.id,
        skip=skip,
        limit=limit
    )

    return [WorkflowExecutionResponse.model_validate(e) for e in executions]


@router.get(
    "/executions/{execution_id}",
    response_model=WorkflowExecutionResponse,
    dependencies=[Depends(require_permission("workflow", "read"))]
)
async def get_execution(
    execution_id: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get workflow execution details"""
    repo = WorkflowExecutionRepository(db)
    execution = await repo.get_by_id(execution_id, tenant.id)

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )

    return WorkflowExecutionResponse.model_validate(execution)
