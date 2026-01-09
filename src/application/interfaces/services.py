"""
Service interfaces (ports) for the application layer.

These protocols define the contracts for application services.
Following Dependency Inversion Principle (DIP).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from src.infrastructure.persistence.models.event import Event
    from src.presentation.api.v1.schemas.event import EventCreate


class IHashService(Protocol):
    """Protocol for hash computation services (DIP)"""

    def compute_hash(
        self,
        subject_id: str,
        event_type: str,
        schema_version: int,
        event_time: datetime,
        payload: dict[str, Any],
        previous_hash: str | None,
    ) -> str:
        """Compute hash for event data"""
        ...


class IEventService(Protocol):
    """Protocol for event service (DIP)"""

    async def create_event(
        self, tenant_id: str, data: EventCreate, *, trigger_workflows: bool = True
    ) -> Event:
        """Create a new event with cryptographic chaining"""
        ...
