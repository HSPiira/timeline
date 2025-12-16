import jsonschema
from typing import Optional
from core.protocols import IEventRepository, IHashService
from schemas.event import EventCreate
from repositories.event_schema_repo import EventSchemaRepository


class EventService:
    """Event service following DIP - depends on abstractions, not concretions"""

    def __init__(
        self,
        event_repo: IEventRepository,
        hash_service: IHashService,
        schema_repo: Optional[EventSchemaRepository] = None
    ):
        self.event_repo = event_repo
        self.hash_service = hash_service
        self.schema_repo = schema_repo

    async def create_event(self, tenant_id: str, data: EventCreate):
        """Create a new event with cryptographic chaining and optional schema validation"""
        # Validate payload against active schema if schema_repo is available
        if self.schema_repo:
            await self._validate_payload(tenant_id, data.event_type, data.payload)

        # Get previous hash for this subject within the tenant
        prev_hash = await self.event_repo.get_last_hash(data.subject_id, tenant_id)

        # Compute event hash
        event_hash = self.hash_service.compute_hash(
            tenant_id,
            data.subject_id,
            data.event_type,
            data.event_time,
            data.payload,
            prev_hash,
        )

        # Create event with hash
        return await self.event_repo.create_event(tenant_id, data, event_hash, prev_hash)

    async def _validate_payload(self, tenant_id: str, event_type: str, payload: dict) -> None:
        """Validate event payload against active schema"""
        schema = await self.schema_repo.get_active_schema(tenant_id, event_type)

        if schema:
            try:
                jsonschema.validate(instance=payload, schema=schema.schema_json)
            except jsonschema.ValidationError as e:
                raise ValueError(f"Payload validation failed: {e.message}") from e
            except jsonschema.SchemaError as e:
                raise ValueError(f"Invalid schema definition: {e.message}") from e