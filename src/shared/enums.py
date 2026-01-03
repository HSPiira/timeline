"""
Shared enumerations for the Timeline application.

Note: TenantStatus is in src/domain/enums.py as it's a domain concept.
"""

from enum import Enum


class ActorType(str, Enum):
    """Actor type enumeration for event tracking"""

    USER = "user"
    SYSTEM = "system"
    EXTERNAL = "external"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid values"""
        return [actor.value for actor in cls]


class DocumentAccessLevel(str, Enum):
    """Document access level enumeration"""

    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid values"""
        return [level.value for level in cls]


class OAuthStatus(str, Enum):
    """OAuth account status enumeration"""

    ACTIVE = "active"
    CONSENT_DENIED = "consent_denied"
    REFRESH_FAILED = "refresh_failed"
    REVOKED = "revoked"
    EXPIRED = "expired"
    UNKNOWN = "unknown"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid values"""
        return [status.value for status in cls]


class WorkflowExecutionStatus(str, Enum):
    """Workflow execution status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid values"""
        return [status.value for status in cls]


class AuditAction(str, Enum):
    """Audit action types for system event tracking"""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ARCHIVED = "archived"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid values"""
        return [action.value for action in cls]
