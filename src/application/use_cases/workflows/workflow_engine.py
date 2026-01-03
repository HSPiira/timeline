"""
Workflow automation engine.

Executes workflows triggered by events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from src.shared.telemetry.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.application.use_cases.events.create_event import EventService
    from src.infrastructure.persistence.models.event import Event
    from src.infrastructure.persistence.models.workflow import (
        Workflow, WorkflowExecution)

logger = get_logger(__name__)


class WorkflowEngine:
    """Execute workflows triggered by events"""

    def __init__(self, db: "AsyncSession", event_service: "EventService"):
        self.db = db
        self.event_service = event_service

    async def process_event_triggers(self, event: "Event", tenant_id: str) -> list["WorkflowExecution"]:
        """
        Find and execute workflows triggered by event.

        Args:
            event: Event that was created
            tenant_id: Tenant ID

        Returns:
            List of workflow executions
        """

        # Find matching workflows
        workflows = await self._find_matching_workflows(
            event_type=event.event_type, tenant_id=tenant_id
        )

        executions: list["WorkflowExecution"] = []
        for workflow in workflows:
            # Check conditions
            if not self._evaluate_conditions(workflow, event):
                continue

            # Execute workflow
            execution = await self._execute_workflow(workflow, event)
            executions.append(execution)

        return executions

    async def _find_matching_workflows(self, event_type: str, tenant_id: str) -> list["Workflow"]:
        """Find active workflows for event type"""
        from src.infrastructure.persistence.models.workflow import Workflow

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

    def _evaluate_conditions(self, workflow: "Workflow", event: "Event") -> bool:
        """Check if event matches workflow conditions"""
        if not workflow.trigger_conditions:
            return True  # No conditions = always match

        # Simple payload field matching
        for key, expected_value in workflow.trigger_conditions.items():
            if key.startswith("payload."):
                field = key.replace("payload.", "")
                actual_value = event.payload.get(field)
                if actual_value != expected_value:
                    return False

        return True

    async def _execute_workflow(self, workflow: "Workflow", triggered_by: "Event") -> "WorkflowExecution":
        """Execute workflow actions"""
        from src.infrastructure.persistence.models.workflow import \
            WorkflowExecution
        from src.presentation.api.v1.schemas.event import EventCreate

        logger.info(
            "Executing workflow '%s' (id: %s) triggered by event %s",
            workflow.name,
            workflow.id,
            triggered_by.id
        )

        execution = WorkflowExecution(
            tenant_id=workflow.tenant_id,
            workflow_id=workflow.id,
            triggered_by_event_id=triggered_by.id,
            triggered_by_subject_id=triggered_by.subject_id,
            status="running",
            started_at=datetime.now(UTC),
        )

        self.db.add(execution)
        await self.db.flush()

        execution_log: list[dict[str, Any]] = []
        actions_executed = 0
        actions_failed = 0

        try:
            for action in workflow.actions:
                action_type = action.get("type")

                if action_type == "create_event":
                    # Create new event as action
                    params = action.get("params", {})
                    try:
                        event_create = EventCreate(
                            subject_id=triggered_by.subject_id,
                            event_type=params.get("event_type"),
                            schema_version=params.get("schema_version", 1),
                            event_time=datetime.now(UTC),
                            payload=params.get("payload", {}),
                        )

                        created_event = await self.event_service.create_event(
                            tenant_id=workflow.tenant_id,
                            event=event_create,
                            trigger_workflows=False,  # Prevent infinite loops
                        )

                        execution_log.append(
                            {
                                "action": action_type,
                                "status": "success",
                                "event_id": created_event.id,
                            }
                        )
                        actions_executed += 1
                        logger.debug(
                            "Workflow action created event %s (type: %s)",
                            created_event.id,
                            created_event.event_type
                        )
                    except Exception as e:
                        execution_log.append(
                            {"action": action_type, "status": "failed", "error": str(e)}
                        )
                        actions_failed += 1
                        logger.warning("Workflow action failed: %s - %s", action_type, str(e))
                else:
                    execution_log.append(
                        {
                            "action": action_type,
                            "status": "skipped",
                            "reason": f"Unknown action type: {action_type}",
                        }
                    )
                    logger.warning("Unknown workflow action type: %s", action_type)

            execution.status = "completed"
            logger.info(
                "Workflow execution %s completed: %d succeeded, %d failed",
                execution.id,
                actions_executed,
                actions_failed
            )
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            logger.exception("Workflow execution %s failed", execution.id)

        execution.completed_at = datetime.now(UTC)
        execution.actions_executed = actions_executed
        execution.actions_failed = actions_failed
        execution.execution_log = execution_log

        await self.db.flush()
        return execution
