"""
Event domain entity.

This represents the business concept of an event, independent of
how it's stored in the database.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.domain.value_objects.core import (EventChain, EventType, SubjectId,
                                           TenantId)


@dataclass
class EventEntity:
    """
    Domain entity for Event (SRP - business logic separate from persistence)

    This represents the business concept of an event, independent of
    how it's stored in the database.
    """

    id: str
    tenant_id: TenantId
    subject_id: SubjectId
    event_type: EventType
    event_time: datetime
    payload: dict[str, Any]
    chain: EventChain
    created_at: datetime

    def validate(self) -> bool:
        """Validate event business rules"""
        # Event time should not be in the future

        now = datetime.now(UTC)
        event_time = (
            self.event_time if self.event_time.tzinfo else self.event_time.replace(tzinfo=UTC)
        )
        if event_time > now:
            raise ValueError("Event time cannot be in the future")

        # Note: Chain integrity is enforced at EventChain construction time
        # via __post_init__ validation, so no need to check here

        # Payload must not be empty
        if not self.payload:
            raise ValueError("Event payload cannot be empty")

        return True

    def is_genesis_event(self) -> bool:
        """Check if this is the first event in the subject's timeline"""
        return self.chain.is_genesis_event()
