from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from models.event import Event
    from models.event_schema import EventSchema
    from models.subject import Subject
    from schemas.event import EventCreate


class IHashService(Protocol):
    """Protocol for hash computation services (DIP)"""

    def compute_hash(
        self,
        tenant_id: str,
        subject_id: str,
        event_type: str,
        event_time: datetime,
        payload: dict,
        previous_hash: str | None,
    ) -> str:
        """Compute hash for event data"""
        ...


class IEventRepository(Protocol):
    """Protocol for event repository (DIP)"""

    async def get_last_hash(self, subject_id: str, tenant_id: str) -> str | None:
        """Get the hash of the most recent event for a subject within a tenant"""
        ...

    async def get_last_event(self, subject_id: str, tenant_id: str) -> Event | None:
        """Get the most recent event for a subject within a tenant"""
        ...

    async def create_event(
        self,
        tenant_id: str,
        data: EventCreate,
        event_hash: str,
        previous_hash: str | None,
    ) -> Event:
        """Create a new event with computed hash"""
        ...

    async def get_by_id(self, event_id: str) -> Event | None:
        """Get event by ID"""
        ...

    async def get_by_subject(self, subject_id: str, tenant_id: str) -> list[Event]:
        """Get all events for a subject within a tenant"""
        ...


class ISubjectRepository(Protocol):
    """Protocol for subject repository (DIP)"""

    async def get_by_id(self, subject_id: str) -> Subject | None:
        """Get subject by ID"""
        ...

    async def get_by_id_and_tenant(
        self, subject_id: str, tenant_id: str
    ) -> Subject | None:
        """Get subject by ID and verify it belongs to the tenant"""
        ...

    async def get_by_tenant(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> list[Subject]:
        """Get all subjects for a tenant with pagination"""
        ...

    async def get_by_type(
        self, tenant_id: str, subject_type: str, skip: int = 0, limit: int = 100
    ) -> list[Subject]:
        """Get all subjects of a specific type for a tenant"""
        ...

    async def get_by_external_ref(
        self, tenant_id: str, external_ref: str
    ) -> Subject | None:
        """Get subject by external reference"""
        ...


class IEventSchemaRepository(Protocol):
    """Protocol for event schema repository (DIP)"""

    async def get_by_id(self, schema_id: str) -> EventSchema | None:
        """Get schema by ID"""
        ...

    async def get_by_version(
        self, tenant_id: str, event_type: str, version: int
    ) -> EventSchema | None:
        """Get specific schema version"""
        ...

    async def get_active_schema(
        self, tenant_id: str, event_type: str
    ) -> EventSchema | None:
        """Get active schema for event type and tenant"""
        ...

    async def get_all_for_event_type(
        self, tenant_id: str, event_type: str
    ) -> list[EventSchema]:
        """Get all schema versions for event type"""
        ...

    async def get_next_version(self, tenant_id: str, event_type: str) -> int:
        """Get the next version number for an event_type"""
        ...


class IEventService(Protocol):
    """Protocol for event service (DIP)"""

    async def create_event(
        self, tenant_id: str, data: EventCreate, *, trigger_workflows: bool = True
    ) -> Event:
        """Create a new event with cryptographic chaining"""
        ...
