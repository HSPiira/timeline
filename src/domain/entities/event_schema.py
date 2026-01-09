"""
EventSchema domain entity.

Represents the validation contract for event payloads with immutable versioning.
"""

from dataclasses import dataclass
from typing import Any

from src.domain.value_objects.core import EventType


@dataclass
class EventSchemaEntity:
    """
    Domain entity for EventSchema.
    
    Schemas define the structure of event payloads per event_type.
    Immutable versioning: schemas cannot be modified, only new versions created.
    """

    id: str
    tenant_id: str
    event_type: EventType
    schema_definition: dict[str, Any]
    version: int
    is_active: bool
    created_by: str | None = None

    def validate(self) -> bool:
        """Validate schema business rules."""
        if self.version < 1:
            raise ValueError("Schema version must be positive")
        if not self.schema_definition:
            raise ValueError("Schema definition cannot be empty")
        return True

    def can_validate_events(self) -> bool:
        """Only active schemas can be used for new event validation."""
        return self.is_active

    def is_compatible_with(self, previous: "EventSchemaEntity") -> bool:
        """
        Check if this schema is backward-compatible with previous version.
        
        Business rule: New schemas should not break existing event queries.
        This is a simplified check - real implementation would use JSON Schema
        compatibility analysis.
        """
        if previous.event_type.value != self.event_type.value:
            raise ValueError("Cannot compare schemas for different event types")
        
        prev_required = set(previous.schema_definition.get("required", []))
        curr_required = set(self.schema_definition.get("required", []))
        
        new_required = curr_required - prev_required
        if new_required:
            return False
        
        return True

    def activate(self) -> None:
        """
        Activate this schema version.
        
        Business rule: Only one version per event_type can be active.
        Activation of this version should deactivate others (handled in use case).
        """
        if self.is_active:
            raise ValueError("Schema is already active")
        self.is_active = True

    def deactivate(self) -> None:
        """Deactivate this schema version."""
        if not self.is_active:
            raise ValueError("Schema is already inactive")
        self.is_active = False