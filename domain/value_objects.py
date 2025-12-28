import re
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class TenantCode:
    """
    Value object for Tenant Code (SRP - tenant code validation)

    Tenant codes must be:
    - 3-15 characters
    - lowercase
    - alphanumeric with optional hyphen
    - abbreviation-based (not full legal names)
    - immutable once activated
    """

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("Tenant code must be a non-empty string")

        # Length validation
        if len(self.value) < 3 or len(self.value) > 15:
            raise ValueError("Tenant code must be 3-15 characters")

        # Format validation: lowercase alphanumeric with optional hyphens
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", self.value):
            raise ValueError(
                "Tenant code must be lowercase alphanumeric with optional hyphens "
                "(e.g., 'acme', 'acme-corp', 'abc123')"
            )


@dataclass(frozen=True)
class TenantId:
    """Value object for Tenant ID (SRP - single validation responsibility)"""

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("Tenant ID must be a non-empty string")
        if len(self.value) > 255:
            raise ValueError("Tenant ID must not exceed 255 characters")


@dataclass(frozen=True)
class SubjectId:
    """Value object for Subject ID (SRP)"""

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("Subject ID must be a non-empty string")
        if len(self.value) > 255:
            raise ValueError("Subject ID must not exceed 255 characters")


@dataclass(frozen=True)
class EventType:
    """Value object for Event Type with domain validation (SRP)"""

    value: str

    # Standard event types (reference only - custom types are allowed)
    VALID_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "created",
            "updated",
            "deleted",
            "status_changed",
            "metadata_updated",
            "relationship_added",
            "relationship_removed",
        }
    )

    def __post_init__(self):
        if not self.value or not isinstance(self.value, str):
            raise ValueError("Event type must be a non-empty string")
        # Note: We allow custom event types for extensibility
        # VALID_TYPES serves as documentation for standard types


@dataclass(frozen=True)
class Hash:
    """Value object for cryptographic hash (SRP)"""

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("Hash must be a non-empty string")
        # SHA-256 produces 64 hex characters
        if len(self.value) not in (64, 128):  # SHA-256 or SHA-512
            raise ValueError(
                "Hash must be a valid SHA-256 (64 chars) or SHA-512 (128 chars) hex string"
            )
        if not all(c in "0123456789abcdef" for c in self.value.lower()):
            raise ValueError("Hash must contain only hexadecimal characters")


@dataclass(frozen=True)
class EventChain:
    """Value object representing the chain relationship (SRP)"""

    current_hash: Hash
    previous_hash: Hash | None

    def __post_init__(self):
        """Enforce chain invariants at construction time"""
        # Invariant 1: current_hash must always exist
        if self.current_hash is None:
            raise ValueError("current_hash is required")

        # Invariant 2: For non-genesis events, previous_hash must not equal current_hash
        # (prevents self-referencing loops)
        if self.previous_hash is not None:
            if self.current_hash.value == self.previous_hash.value:
                raise ValueError(
                    "current_hash cannot reference itself (current_hash == previous_hash)"
                )

    def is_genesis_event(self) -> bool:
        """Check if this is the first event in the chain"""
        return self.previous_hash is None
