"""Workflow automation engine - MVP implementation"""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from models.event import Event
from models.workflow import Workflow, WorkflowExecution
from schemas.event import EventCreate
from services.event_service import EventService

logger = get_logger(__name__)


class WorkflowEngine:
    """Execute workflows triggered by events"""

    def __init__(self, db: AsyncSession, event_service: EventService):
        self.db = db
        self.event_service = event_service

    async def process_event_triggers(
        self, event: Event, tenant_id: str
    ) -> list[WorkflowExecution]:
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

        executions = []
        for workflow in workflows:
            # Check conditions
            if not self._evaluate_conditions(workflow, event):
                continue

            # Execute workflow
            execution = await self._execute_workflow(workflow, event)
            executions.append(execution)

        return executions

    async def _find_matching_workflows(
        self, event_type: str, tenant_id: str
    ) -> list[Workflow]:
        """Find active workflows for event type"""
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

    def _evaluate_conditions(self, workflow: Workflow, event: Event) -> bool:
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

    async def _execute_workflow(
        self, workflow: Workflow, triggered_by: Event
    ) -> WorkflowExecution:
        """Execute workflow actions"""
        logger.info(
            f"Executing workflow '{workflow.name}' (id: {workflow.id}) "
            f"triggered by event {triggered_by.id}"
        )

        execution = WorkflowExecution(
            tenant_id=workflow.tenant_id,
            workflow_id=workflow.id,
            triggered_by_event_id=triggered_by.id,
            triggered_by_subject_id=triggered_by.subject_id,
            status="running",
            started_at=datetime.utcnow(),
        )

        self.db.add(execution)
        await self.db.flush()

        execution_log = []
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
                            f"Workflow action created event {created_event.id} "
                            f"(type: {created_event.event_type})"
                        )
                    except Exception as e:
                        execution_log.append(
                            {"action": action_type, "status": "failed", "error": str(e)}
                        )
                        actions_failed += 1
                        logger.warning(
                            f"Workflow action failed: {action_type} - {str(e)}"
                        )
                else:
                    execution_log.append(
                        {
                            "action": action_type,
                            "status": "skipped",
                            "reason": f"Unknown action type: {action_type}",
                        }
                    )
                    logger.warning(f"Unknown workflow action type: {action_type}")

            execution.status = "completed"
            logger.info(
                f"Workflow execution {execution.id} completed: "
                f"{actions_executed} succeeded, {actions_failed} failed"
            )
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            logger.error(
                f"Workflow execution {execution.id} failed: {str(e)}", exc_info=True
            )

        execution.completed_at = datetime.utcnow()
        execution.actions_executed = actions_executed
        execution.actions_failed = actions_failed
        execution.execution_log = execution_log

        await self.db.flush()
        return execution
