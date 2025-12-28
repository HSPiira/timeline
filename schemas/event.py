from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class EventCreate(BaseModel):
    subject_id: str
    event_type: str
    schema_version: int  # Required - must match an active schema version
    event_time: datetime
    payload: dict

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("Event type must be a non-empty string")
        if not v.replace("_", "").isalnum():
            raise ValueError(
                "Event type must contain only alphanumeric characters and underscores"
            )
        return v.lower()

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Schema version must be >= 1")
        return v

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, v: datetime) -> datetime:
        if v > datetime.now(v.tzinfo):
            raise ValueError("Event time cannot be in the future")
        return v

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError("Event payload cannot be empty")
        return v


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

    model_config = ConfigDict(from_attributes=True)
