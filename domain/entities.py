from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
from domain.value_objects import (
    TenantId,
    SubjectId,
    EventType,
    Hash,
    EventChain
)
from core.enums import TenantStatus


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
    payload: Dict[str, Any]
    chain: EventChain
    created_at: datetime

    def validate(self) -> bool:
        """Validate event business rules"""
        # Event time should not be in the future
        if self.event_time > datetime.now(self.event_time.tzinfo):
            raise ValueError("Event time cannot be in the future")

        # Validate chain integrity
        if not self.chain.validate_chain():
            raise ValueError("Invalid event chain structure")

        # Payload must not be empty
        if not self.payload:
            raise ValueError("Event payload cannot be empty")

        return True

    def is_genesis_event(self) -> bool:
        """Check if this is the first event in the subject's timeline"""
        return self.chain.is_genesis_event()


@dataclass
class TenantEntity:
    """
    Domain entity for Tenant (SRP - business logic separate from persistence)
    """
    id: TenantId
    code: str
    name: str
    status: TenantStatus
    created_at: datetime

    def can_create_events(self) -> bool:
        """Business rule: only active tenants can create events"""
        return self.status == TenantStatus.ACTIVE

    def activate(self) -> None:
        """Activate tenant"""
        self.status = TenantStatus.ACTIVE

    def suspend(self) -> None:
        """Suspend tenant"""
        self.status = TenantStatus.SUSPENDED

    def archive(self) -> None:
        """Archive tenant"""
        self.status = TenantStatus.ARCHIVED
