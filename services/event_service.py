from __future__ import annotations

from typing import TYPE_CHECKING

import jsonschema

from core.logging import get_logger
from core.protocols import (
    IEventRepository,
    IEventSchemaRepository,
    IHashService,
    ISubjectRepository,
)
from models.event import Event
from schemas.event import EventCreate

if TYPE_CHECKING:
    from models.workflow import WorkflowExecution
    from services.workflow_engine import WorkflowEngine

logger = get_logger(__name__)


class EventService:
    """Event service following DIP - depends on abstractions, not concretions"""

    def __init__(
        self,
        event_repo: IEventRepository,
        hash_service: IHashService,
        subject_repo: ISubjectRepository,
        schema_repo: IEventSchemaRepository | None = None,
        workflow_engine: WorkflowEngine | None = None,
    ) -> None:
        self.event_repo = event_repo
        self.hash_service = hash_service
        self.subject_repo = subject_repo
        self.schema_repo = schema_repo
        self.workflow_engine = workflow_engine

    async def create_event(
        self, tenant_id: str, event: EventCreate, *, trigger_workflows: bool = True
    ) -> Event:
        """
        Create a new event with cryptographic chaining and schema validation.

        Args:
            tenant_id: The tenant ID
            event: Event creation data
            trigger_workflows: Whether to trigger workflows (default True)

        Returns:
            Created event with computed hash

        Raises:
            ValueError: If subject doesn't exist or schema validation fails
        """
        # 1. Validate that subject exists and belongs to tenant
        subject = await self.subject_repo.get_by_id_and_tenant(
            event.subject_id, tenant_id
        )

        if not subject:
            raise ValueError(
                f"Subject '{event.subject_id}' not found or does not belong to tenant"
            )

        # 2. Validate schema_version exists and validate payload against it
        if self.schema_repo:
            await self._validate_payload(
                tenant_id, event.event_type, event.schema_version, event.payload
            )

        # 3. Get the previous event for this subject (for chaining and validation)
        prev_event = await self.event_repo.get_last_event(event.subject_id, tenant_id)
        prev_hash = prev_event.hash if prev_event else None

        # 4. Validate temporal ordering (prevent tampering)
        if prev_event and event.event_time <= prev_event.event_time:
            raise ValueError(
                f"Event time {event.event_time} must be after previous event time {prev_event.event_time}. "
                f"This prevents tampering with the event chain."
            )

        # 5. Compute hash using previous event's hash
        event_hash = self.hash_service.compute_hash(
            tenant_id,
            event.subject_id,
            event.event_type,
            event.event_time,
            event.payload,
            prev_hash,
        )

        # 6. Create the event
        created_event = await self.event_repo.create_event(
            tenant_id, event, event_hash, prev_hash
        )

        # 7. Trigger workflows if enabled
        if trigger_workflows:
            await self._trigger_workflows(created_event, tenant_id)

        return created_event

    async def _trigger_workflows(
        self, event: Event, tenant_id: str
    ) -> list[WorkflowExecution]:
        """
        Trigger workflows for created event.

        Args:
            event: Created event
            tenant_id: Tenant ID

        Returns:
            List of workflow executions
        """
        if not self.workflow_engine:
            return []

        try:
            executions = await self.workflow_engine.process_event_triggers(
                event, tenant_id
            )
            if executions:
                logger.info(
                    "Triggered %d workflow(s) for event %s (type: %s)",
                    len(executions),
                    event.id,
                    event.event_type,
                )
            return executions
        except Exception:
            logger.exception(
                "Workflow trigger failed for event %s (type: %s)",
                event.id,
                event.event_type,
            )
            return []

    async def _validate_payload(
        self, tenant_id: str, event_type: str, schema_version: int, payload: dict
    ) -> None:
        """
        Validate event payload against specific schema version.

        Raises:
            ValueError: If schema version doesn't exist, is inactive, or validation fails
        """
        if not self.schema_repo:
            raise ValueError("Schema repository not configured")

        # Get the specific schema version
        schema = await self.schema_repo.get_by_version(
            tenant_id, event_type, schema_version
        )

        if not schema:
            raise ValueError(
                f"Schema version {schema_version} not found for event type '{event_type}'"
            )

        # Validate that schema is active (only active schemas can be used for new events)
        if not schema.is_active:
            raise ValueError(
                f"Schema version {schema_version} for event type '{event_type}' is not active. "
                f"Please activate it or use an active version."
            )

        # Validate payload against schema
        try:
            jsonschema.validate(instance=payload, schema=schema.schema_definition)
        except jsonschema.ValidationError as e:
            raise ValueError(
                f"Payload validation failed against schema v{schema_version}: {e.message}"
            ) from e
        except jsonschema.SchemaError as e:
            raise ValueError(
                f"Invalid schema definition for v{schema_version}: {e.message}"
            ) from e
