from typing import Protocol, Optional, List
from datetime import datetime
from models.event import Event
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

    async def get_last_hash(self, subject_id: str) -> Optional[str]:
        """Get the hash of the most recent event for a subject"""
        ...

    async def create_event(
        self,
        tenant_id: str,
        data: EventCreate,
        event_hash: str,
        previous_hash: Optional[str]
    ) -> Event:
        """Create a new event with computed hash"""
        ...

    async def get_by_id(self, event_id: str) -> Optional[Event]:
        """Get event by ID"""
        ...

    async def get_by_subject(self, subject_id: str) -> List[Event]:
        """Get all events for a subject"""
        ...


class IEventService(Protocol):
    """Protocol for event service (DIP)"""

    async def create_event(self, tenant_id: str, data: EventCreate) -> Event:
        """Create a new event with cryptographic chaining"""
        ...
