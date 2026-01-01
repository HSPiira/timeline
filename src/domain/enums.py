"""Domain enumerations for the Timeline application."""

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
