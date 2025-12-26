from typing import Protocol, Optional, List, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from models.event import Event
    from models.subject import Subject
    from models.event_schema import EventSchema
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
        previous_hash: Optional[str]
    ) -> str:
        """Compute hash for event data"""
        ...


class IEventRepository(Protocol):
    """Protocol for event repository (DIP)"""

    async def get_last_hash(self, subject_id: str, tenant_id: str) -> Optional[str]:
        """Get the hash of the most recent event for a subject within a tenant"""
        ...

    async def get_last_event(
        self, subject_id: str, tenant_id: str
    ) -> Optional["Event"]:
        """Get the most recent event for a subject within a tenant"""
        ...

    async def create_event(
        self,
        tenant_id: str,
        data: "EventCreate",
        event_hash: str,
        previous_hash: Optional[str]
    ) -> "Event":
        """Create a new event with computed hash"""
        ...

    async def get_by_id(self, event_id: str) -> Optional["Event"]:
        """Get event by ID"""
        ...

    async def get_by_subject(
        self, subject_id: str, tenant_id: str
    ) -> List["Event"]:
        """Get all events for a subject within a tenant"""
        ...


class ISubjectRepository(Protocol):
    """Protocol for subject repository (DIP)"""

    async def get_by_id(self, subject_id: str) -> Optional["Subject"]:
        """Get subject by ID"""
        ...

    async def get_by_id_and_tenant(
        self, subject_id: str, tenant_id: str
    ) -> Optional["Subject"]:
        """Get subject by ID and verify it belongs to the tenant"""
        ...

    async def get_by_tenant(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> List["Subject"]:
        """Get all subjects for a tenant with pagination"""
        ...

    async def get_by_type(
        self,
        tenant_id: str,
        subject_type: str,
        skip: int = 0,
        limit: int = 100
    ) -> List["Subject"]:
        """Get all subjects of a specific type for a tenant"""
        ...

    async def get_by_external_ref(
        self, tenant_id: str, external_ref: str
    ) -> Optional["Subject"]:
        """Get subject by external reference"""
        ...


class IEventSchemaRepository(Protocol):
    """Protocol for event schema repository (DIP)"""

    async def get_by_id(self, schema_id: str) -> Optional["EventSchema"]:
        """Get schema by ID"""
        ...

    async def get_by_version(
        self, tenant_id: str, event_type: str, version: int
    ) -> Optional["EventSchema"]:
        """Get specific schema version"""
        ...

    async def get_active_schema(
        self, tenant_id: str, event_type: str
    ) -> Optional["EventSchema"]:
        """Get active schema for event type and tenant"""
        ...

    async def get_all_for_event_type(
        self, tenant_id: str, event_type: str
    ) -> List["EventSchema"]:
        """Get all schema versions for event type"""
        ...

    async def get_next_version(self, tenant_id: str, event_type: str) -> int:
        """Get the next version number for an event_type"""
        ...


class IEventService(Protocol):
    """Protocol for event service (DIP)"""

    async def create_event(
        self,
        tenant_id: str,
        data: "EventCreate",
        *,
        trigger_workflows: bool = True
    ) -> "Event":
        """Create a new event with cryptographic chaining"""
        ...
