"""
Event creation use case.

Orchestrates event creation with cryptographic chaining and schema validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import jsonschema

from src.shared.telemetry.logging import get_logger

if TYPE_CHECKING:
    from src.application.interfaces.repositories import (
        IEventRepository, IEventSchemaRepository, ISubjectRepository)
    from src.application.interfaces.services import IHashService
    from src.application.use_cases.workflows.workflow_engine import \
        WorkflowEngine
    from src.infrastructure.persistence.models.event import Event
    from src.infrastructure.persistence.models.workflow import \
        WorkflowExecution
    from src.presentation.api.v1.schemas.event import EventCreate

logger = get_logger(__name__)


class EventService:
    """Event service following DIP - depends on abstractions, not concretions"""

    def __init__(
        self,
        event_repo: "IEventRepository",
        hash_service: "IHashService",
        subject_repo: "ISubjectRepository",
        schema_repo: "IEventSchemaRepository | None" = None,
        workflow_engine: "WorkflowEngine | None" = None,
    ) -> None:
        self.event_repo = event_repo
        self.hash_service = hash_service
        self.subject_repo = subject_repo
        self.schema_repo = schema_repo
        self.workflow_engine = workflow_engine

    async def create_event(
        self, tenant_id: str, event: "EventCreate", *, trigger_workflows: bool = True
    ) -> "Event":
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
        subject = await self.subject_repo.get_by_id_and_tenant(event.subject_id, tenant_id)

        if not subject:
            raise ValueError(f"Subject '{event.subject_id}' not found or does not belong to tenant")

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
                f"Event time {event.event_time} must be after "
                f"previous event time {prev_event.event_time}. "
                f"This prevents tampering with the event chain."
            )

        # 5. Compute hash using previous event's hash
        event_hash = self.hash_service.compute_hash(
            subject_id=event.subject_id,
            event_type=event.event_type,
            schema_version=event.schema_version,
            event_time=event.event_time,
            payload=event.payload,
            previous_hash=prev_hash,
        )

        # 6. Create the event
        created_event = await self.event_repo.create_event(tenant_id, event, event_hash, prev_hash)

        # 7. Trigger workflows if enabled
        if trigger_workflows:
            await self._trigger_workflows(created_event, tenant_id)

        return created_event

    async def _trigger_workflows(self, event: "Event", tenant_id: str) -> list["WorkflowExecution"]:
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
            executions = await self.workflow_engine.process_event_triggers(event, tenant_id)
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

    async def create_events_bulk(
        self,
        tenant_id: str,
        events: list["EventCreate"],
        *,
        skip_schema_validation: bool = False,
        trigger_workflows: bool = False,
    ) -> list["Event"]:
        """
        Create multiple events with cryptographic chaining in a single batch.

        Optimized for bulk operations like email sync. Computes hashes sequentially
        (required for chain integrity) but inserts all events in a single DB roundtrip.

        Args:
            tenant_id: The tenant ID
            events: List of event creation data (must be sorted by event_time)
            skip_schema_validation: Skip schema validation for performance
            trigger_workflows: Whether to trigger workflows (default False for bulk)

        Returns:
            List of created events with computed hashes

        Performance:
            - Hash computation: O(n) sequential (chain requirement)
            - DB insert: 1 roundtrip instead of N
            - 5-10x faster for batches of 100+ events
        """
        from src.infrastructure.persistence.models.event import Event

        if not events:
            return []

        # Validate subject exists (only need to check once for same subject)
        subject_ids = {e.subject_id for e in events}
        for subject_id in subject_ids:
            subject = await self.subject_repo.get_by_id_and_tenant(subject_id, tenant_id)
            if not subject:
                raise ValueError(f"Subject '{subject_id}' not found or does not belong to tenant")

        # Get the last event for chain initialization
        # Assumes all events are for the same subject (common in email sync)
        first_subject_id = events[0].subject_id
        prev_event = await self.event_repo.get_last_event(first_subject_id, tenant_id)
        prev_hash = prev_event.hash if prev_event else None
        prev_time = prev_event.event_time if prev_event else None

        # Build event objects with sequential hash computation
        event_objects: list[Event] = []

        for event_data in events:
            # Validate temporal ordering
            if prev_time and event_data.event_time <= prev_time:
                raise ValueError(
                    f"Event time {event_data.event_time} must be after "
                    f"previous event time {prev_time}. Events must be sorted."
                )

            # Optional schema validation
            if not skip_schema_validation and self.schema_repo:
                await self._validate_payload(
                    tenant_id, event_data.event_type, event_data.schema_version, event_data.payload
                )

            # Compute hash using previous event's hash (chain requirement)
            event_hash = self.hash_service.compute_hash(
                subject_id=event_data.subject_id,
                event_type=event_data.event_type,
                schema_version=event_data.schema_version,
                event_time=event_data.event_time,
                payload=event_data.payload,
                previous_hash=prev_hash,
            )

            # Create event object
            event_obj = Event(
                tenant_id=tenant_id,
                subject_id=event_data.subject_id,
                event_type=event_data.event_type,
                schema_version=event_data.schema_version,
                event_time=event_data.event_time,
                payload=event_data.payload,
                hash=event_hash,
                previous_hash=prev_hash,
            )
            event_objects.append(event_obj)

            # Update chain state for next iteration
            prev_hash = event_hash
            prev_time = event_data.event_time

        # Bulk insert all events
        created_events = await self.event_repo.create_events_bulk(event_objects)

        logger.info("Bulk created %d events for tenant %s", len(created_events), tenant_id)

        # Optionally trigger workflows (usually disabled for bulk)
        if trigger_workflows:
            for event in created_events:
                await self._trigger_workflows(event, tenant_id)

        return created_events

    async def _validate_payload(
        self, tenant_id: str, event_type: str, schema_version: int, payload: dict[str, Any]
    ) -> None:
        """
        Validate event payload against specific schema version.

        Raises:
            ValueError: If schema version doesn't exist, is inactive, or validation fails
        """
        if not self.schema_repo:
            raise ValueError("Schema repository not configured")

        # Get the specific schema version
        schema = await self.schema_repo.get_by_version(tenant_id, event_type, schema_version)

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
            raise ValueError(f"Invalid schema definition for v{schema_version}: {e.message}") from e
