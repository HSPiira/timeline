"""Repository for workflow data access"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.workflow import Workflow, WorkflowExecution


class WorkflowRepository:
    """Repository for Workflow model"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, workflow: Workflow) -> Workflow:
        """Create new workflow"""
        self.db.add(workflow)
        await self.db.flush()
        await self.db.refresh(workflow)
        return workflow

    async def get_by_id(self, workflow_id: str, tenant_id: str) -> Workflow | None:
        """Get workflow by ID and tenant"""
        stmt = select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.tenant_id == tenant_id,
            Workflow.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_tenant(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> list[Workflow]:
        """Get all workflows for tenant"""
        stmt = select(Workflow).where(
            Workflow.tenant_id == tenant_id, Workflow.deleted_at.is_(None)
        )

        if not include_inactive:
            stmt = stmt.where(Workflow.is_active.is_(True))

        stmt = stmt.order_by(Workflow.execution_order.asc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_trigger(self, tenant_id: str, event_type: str) -> list[Workflow]:
        """Get active workflows for event type"""
        stmt = (
            select(Workflow)
            .where(
                Workflow.tenant_id == tenant_id,
                Workflow.trigger_event_type == event_type,
                Workflow.is_active.is_(True),
                Workflow.deleted_at.is_(None),
            )
            .order_by(Workflow.execution_order.asc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, workflow: Workflow) -> Workflow:
        """Update workflow"""
        await self.db.flush()
        await self.db.refresh(workflow)
        return workflow

    async def soft_delete(self, workflow_id: str, tenant_id: str) -> bool:
        """Soft delete workflow"""
        workflow = await self.get_by_id(workflow_id, tenant_id)
        if not workflow:
            return False

        from datetime import datetime

        workflow.deleted_at = datetime.utcnow()
        await self.db.flush()
        return True


class WorkflowExecutionRepository:
    """Repository for WorkflowExecution model"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, execution: WorkflowExecution) -> WorkflowExecution:
        """Create execution record"""
        self.db.add(execution)
        await self.db.flush()
        await self.db.refresh(execution)
        return execution

    async def get_by_id(
        self, execution_id: str, tenant_id: str
    ) -> WorkflowExecution | None:
        """Get execution by ID"""
        stmt = select(WorkflowExecution).where(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.tenant_id == tenant_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_workflow(
        self, workflow_id: str, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> list[WorkflowExecution]:
        """Get executions for workflow"""
        stmt = (
            select(WorkflowExecution)
            .where(
                WorkflowExecution.workflow_id == workflow_id,
                WorkflowExecution.tenant_id == tenant_id,
            )
            .order_by(WorkflowExecution.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_event(
        self, event_id: str, tenant_id: str
    ) -> list[WorkflowExecution]:
        """Get executions triggered by event"""
        stmt = (
            select(WorkflowExecution)
            .where(
                WorkflowExecution.triggered_by_event_id == event_id,
                WorkflowExecution.tenant_id == tenant_id,
            )
            .order_by(WorkflowExecution.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())
