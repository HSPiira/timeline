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
