"""Repository for workflow data access"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.workflow import (Workflow,
                                                            WorkflowExecution)
from src.infrastructure.persistence.repositories.auditable_repo import AuditableRepository
from src.shared.enums import AuditAction

if TYPE_CHECKING:
    from src.application.services.system_audit_service import SystemAuditService


class WorkflowRepository(AuditableRepository[Workflow]):
    """Repository for Workflow model with automatic audit tracking."""

    def __init__(
        self,
        db: AsyncSession,
        audit_service: "SystemAuditService | None" = None,
        *,
        enable_audit: bool = True,
    ):
        super().__init__(db, Workflow, audit_service, enable_audit=enable_audit)

    # Auditable implementation
    def _get_entity_type(self) -> str:
        return "workflow"

    def _get_tenant_id(self, obj: Workflow) -> str:
        return obj.tenant_id

    def _serialize_for_audit(self, obj: Workflow) -> dict[str, Any]:
        return {
            "id": obj.id,
            "name": obj.name,
            "description": obj.description,
            "trigger_event_type": obj.trigger_event_type,
            "is_active": obj.is_active,
            "execution_order": obj.execution_order,
        }

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

    async def soft_delete(self, workflow_id: str, tenant_id: str) -> bool:
        """Soft delete workflow with audit event."""
        workflow = await self.get_by_id(workflow_id, tenant_id)
        if not workflow:
            return False

        workflow.deleted_at = datetime.now(UTC)
        await self.db.flush()
        # Emit deleted audit event
        await self._emit_audit_event(AuditAction.DELETED, workflow)
        return True

    async def activate(self, workflow_id: str, tenant_id: str) -> Workflow | None:
        """Activate a workflow with audit event."""
        workflow = await self.get_by_id(workflow_id, tenant_id)
        if not workflow:
            return None

        workflow.is_active = True
        await self.update(workflow)
        await self.emit_custom_audit(workflow, AuditAction.ACTIVATED)
        return workflow

    async def deactivate(self, workflow_id: str, tenant_id: str) -> Workflow | None:
        """Deactivate a workflow with audit event."""
        workflow = await self.get_by_id(workflow_id, tenant_id)
        if not workflow:
            return None

        workflow.is_active = False
        await self.update(workflow)
        await self.emit_custom_audit(workflow, AuditAction.DEACTIVATED)
        return workflow


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

    async def get_by_id(self, execution_id: str, tenant_id: str) -> WorkflowExecution | None:
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

    async def get_by_event(self, event_id: str, tenant_id: str) -> list[WorkflowExecution]:
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
