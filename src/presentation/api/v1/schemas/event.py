import json
import os
# Import sanitization utilities
import sys
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.shared.utils.sanitization import sanitize_input, validate_identifier

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class EventCreate(BaseModel):
    subject_id: str
    event_type: str
    schema_version: int  # Required - must match an active schema version
    event_time: datetime
    payload: dict[str, Any]

    @field_validator("subject_id")
    @classmethod
    def validate_subject_id(cls, v: str) -> str:
        """Validate subject ID format."""
        if not v or not isinstance(v, str):
            raise ValueError("Subject ID must be a non-empty string")
        return validate_identifier(v)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Validate and normalize event type."""
        if not v or not isinstance(v, str):
            raise ValueError("Event type must be a non-empty string")

        # Validate format
        validated = validate_identifier(v.lower())

        # Check length
        if len(validated) > 50:
            raise ValueError("Event type must be 50 characters or less")

        return validated

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: int) -> int:
        """Validate schema version."""
        if v < 1 or v > 1000:
            raise ValueError("Schema version must be between 1 and 1000")
        return v

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, v: datetime) -> datetime:
        """Validate event time."""
        if v > datetime.now(v.tzinfo):
            raise ValueError("Event time cannot be in the future")

        # Check if too old (e.g., more than 10 years)
        years_ago = (
            datetime.now(v.tzinfo).year - v.year if v.tzinfo else datetime.now().year - v.year
        )
        if years_ago > 10:
            raise ValueError("Event time cannot be more than 10 years in the past")

        return v

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitize payload."""
        if not v:
            raise ValueError("Event payload cannot be empty")

        # Check payload size (e.g., 1MB limit)
        payload_size = len(json.dumps(v))
        if payload_size > 1024 * 1024:  # 1MB
            raise ValueError("Event payload exceeds 1MB limit")

        # Sanitize payload content
        return sanitize_input(v)

    @model_validator(mode="after")
    def validate_model(self) -> "EventCreate":
        """Additional model-level validation."""
        # Example: Check business rules
        if self.event_type == "system_event" and self.schema_version < 2:
            raise ValueError("System events require schema version 2 or higher")

        return self


class EventResponse(BaseModel):
    id: str
    tenant_id: str
    subject_id: str
    event_type: str
    schema_version: int
    event_time: datetime
    payload: dict[str, Any]
    hash: str
    previous_hash: str | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "id": "clh1234567890abcdef",
                "tenant_id": "tenant_123",
                "subject_id": "subject_456",
                "event_type": "user_action",
                "schema_version": 1,
                "event_time": "2024-01-01T12:00:00Z",
                "payload": {"action": "login", "ip": "192.168.1.1"},
                "hash": "sha256_hash_here",
                "previous_hash": "previous_sha256_hash",
                "created_at": "2024-01-01T12:00:00Z",
            }
        },
    )
