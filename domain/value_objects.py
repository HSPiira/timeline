from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass(frozen=True)
class TenantId:
    """Value object for Tenant ID (SRP - single validation responsibility)"""
    value: str

    def __post_init__(self):
        if not self.value or not isinstance(self.value, str):
            raise ValueError("Tenant ID must be a non-empty string")
        if len(self.value) > 255:
            raise ValueError("Tenant ID must not exceed 255 characters")


@dataclass(frozen=True)
class SubjectId:
    """Value object for Subject ID (SRP)"""
    value: str

    def __post_init__(self):
        if not self.value or not isinstance(self.value, str):
            raise ValueError("Subject ID must be a non-empty string")
        if len(self.value) > 255:
            raise ValueError("Subject ID must not exceed 255 characters")


@dataclass(frozen=True)
class EventType:
    """Value object for Event Type with domain validation (SRP)"""
    value: str

    VALID_TYPES = {
        "created",
        "updated",
        "deleted",
        "status_changed",
        "metadata_updated",
        "relationship_added",
        "relationship_removed",
    }

    def __post_init__(self):
        if not self.value or not isinstance(self.value, str):
            raise ValueError("Event type must be a non-empty string")
        # Note: We allow custom event types for extensibility
        # but provide standard types as a reference


@dataclass(frozen=True)
class Hash:
    """Value object for cryptographic hash (SRP)"""
    value: str

    def __post_init__(self):
        if not self.value or not isinstance(self.value, str):
            raise ValueError("Hash must be a non-empty string")
        # SHA-256 produces 64 hex characters
        if len(self.value) not in (64, 128):  # SHA-256 or SHA-512
            raise ValueError("Hash must be a valid SHA-256 (64 chars) or SHA-512 (128 chars) hex string")
        if not all(c in '0123456789abcdef' for c in self.value.lower()):
            raise ValueError("Hash must contain only hexadecimal characters")


@dataclass(frozen=True)
class EventChain:
    """Value object representing the chain relationship (SRP)"""
    current_hash: Hash
    previous_hash: Optional[Hash]

    def is_genesis_event(self) -> bool:
        """Check if this is the first event in the chain"""
        return self.previous_hash is None

    def validate_chain(self) -> bool:
        """Validate that chain structure is valid"""
        # First event must not have previous hash
        # All other events must have previous hash
        if self.is_genesis_event():
            return True
        return self.previous_hash is not None

