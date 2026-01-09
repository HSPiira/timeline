"""
Subject domain entity.

This represents the business concept of a subject, independent of
how it's stored in the database.
"""

from dataclasses import dataclass, field

from src.domain.value_objects.core import SubjectType

@dataclass
class SubjectEntity:
    """
    Domain entity for Subject (SRP - business logic separate from persistence)
    """

    id: str
    tenant_id: str
    subject_type: SubjectType
    external_ref: str | None

    # Optional: track chain state at domain level
    _event_count: int = field(default=0, repr=False)
    _has_events: bool = field(default=False, repr=False)

    def validate(self) -> bool:
        """Validate subject business rules"""
        if not self.id:
            raise ValueError("Subject ID is required")
        if not self.tenant_id:
            raise ValueError("Subject must belong to a tenant")
        # SubjectType validates itself via __post_init__
        return True

    def belongs_to_tenant(self, tenant_id: str) -> bool:
        """Check if subject belongs to the specified tenant."""
        return self.tenant_id == tenant_id

    def can_receive_events(self) -> bool:
        """
        Business rule: determine if subject can receive new events.
        
        Currently always true, but provides extension point for:
        - Archived subjects that shouldn't receive events
        - Subjects with status lifecycle
        - Rate limiting per subject
        """
        return True

    def is_genesis_subject(self) -> bool:
        """Check if this subject has no events yet (empty timeline)."""
        return not self._has_events

    def mark_has_events(self) -> None:
        """Called when first event is added to this subject."""
        self._has_events = True