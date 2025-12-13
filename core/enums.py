from enum import Enum


class TenantStatus(str, Enum):
    """Tenant status enumeration"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid values"""
        return [status.value for status in cls]


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
