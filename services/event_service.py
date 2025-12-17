import jsonschema
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import select
from core.protocols import IEventRepository, IHashService
from core.logging import get_logger
from schemas.event import EventCreate
from repositories.event_schema_repo import EventSchemaRepository
from models.subject import Subject
from models.event import Event

if TYPE_CHECKING:
    from services.workflow_engine import WorkflowEngine
    from models.workflow import WorkflowExecution

logger = get_logger(__name__)


class EventService:
    """Event service following DIP - depends on abstractions, not concretions"""

    def __init__(
        self,
        event_repo: IEventRepository,
        hash_service: IHashService,
        schema_repo: Optional[EventSchemaRepository] = None,
        workflow_engine: Optional["WorkflowEngine"] = None
    ):
        self.event_repo = event_repo
        self.hash_service = hash_service
        self.schema_repo = schema_repo
        self.workflow_engine = workflow_engine

    async def create_event(
        self,
        tenant_id: str,
        event: EventCreate,
        trigger_workflows: bool = True
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
        result = await self.event_repo.db.execute(
            select(Subject).where(
                Subject.id == event.subject_id,
                Subject.tenant_id == tenant_id
            )
        )
        subject = result.scalar_one_or_none()

        if not subject:
            raise ValueError(
                f"Subject '{event.subject_id}' not found or does not belong to tenant"
            )

        # 2. Get and validate against active schema if one exists
        if self.schema_repo:
            await self._validate_payload(tenant_id, event.event_type, event.payload)

        # 3. Get the previous event hash for this subject (for chaining)
        prev_hash = await self.event_repo.get_last_hash(event.subject_id, tenant_id)

        # 4. Compute hash using previous event's hash
        event_hash = self.hash_service.compute_hash(
            tenant_id,
            event.subject_id,
            event.event_type,
            event.event_time,
            event.payload,
            prev_hash,
        )

        # 5. Create the event
        created_event = await self.event_repo.create_event(
            tenant_id, event, event_hash, prev_hash
        )

        # 6. Trigger workflows if enabled
        if trigger_workflows:
            await self._trigger_workflows(created_event, tenant_id)

        return created_event

    async def _trigger_workflows(
        self,
        event: Event,
        tenant_id: str
    ) -> List["WorkflowExecution"]:
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
                    f"Triggered {len(executions)} workflow(s) for event {event.id} "
                    f"(type: {event.event_type})"
                )
            return executions
        except Exception as e:
            logger.error(
                f"Workflow trigger failed for event {event.id} (type: {event.event_type}): {e}",
                exc_info=True
            )
            return []

    async def _validate_payload(self, tenant_id: str, event_type: str, payload: dict) -> None:
        """Validate event payload against active schema"""
        schema = await self.schema_repo.get_active_schema(tenant_id, event_type)

        if schema:
            try:
                jsonschema.validate(instance=payload, schema=schema.schema_definition)
            except jsonschema.ValidationError as e:
                raise ValueError(f"Payload validation failed: {e.message}") from e
            except jsonschema.SchemaError as e:
                raise ValueError(f"Invalid schema definition: {e.message}") from e