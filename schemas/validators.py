from datetime import datetime
from typing import Any, Dict
from pydantic import field_validator


class EventValidators:
    """Shared validators for event schemas (SRP - validation logic separation)"""

    @staticmethod
    @field_validator('event_time')
    def validate_event_time(cls, v: datetime) -> datetime:
        """Ensure event time is not in the future"""
        if v > datetime.now(v.tzinfo):
            raise ValueError("Event time cannot be in the future")
        return v

    @staticmethod
    @field_validator('payload')
    def validate_payload(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure payload is not empty"""
        if not v:
            raise ValueError("Event payload cannot be empty")
        return v

    @staticmethod
    @field_validator('event_type')
    def validate_event_type(cls, v: str) -> str:
        """Ensure event type is not empty and follows naming convention"""
        if not v or not isinstance(v, str):
            raise ValueError("Event type must be a non-empty string")
        if not v.replace('_', '').isalnum():
            raise ValueError(
                "Event type must contain only alphanumeric characters and underscores"
            )
        return v.lower()


class TenantValidators:
    """Shared validators for tenant schemas (SRP)"""

    @staticmethod
    @field_validator('code')
    def validate_code(cls, v: str) -> str:
        """Ensure tenant code follows naming convention"""
        if not v or not isinstance(v, str):
            raise ValueError("Tenant code must be a non-empty string")
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError(
                "Tenant code must contain only alphanumeric characters, hyphens, and underscores"
            )
        return v.lower()

    @staticmethod
    @field_validator('status')
    def validate_status(cls, v: str) -> str:
        """Ensure status is valid"""
        valid_statuses = {"active", "suspended", "archived"}
        if v not in valid_statuses:
            raise ValueError(
                f"Tenant status must be one of: {', '.join(valid_statuses)}"
            )
        return v
