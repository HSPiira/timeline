from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Any, Dict


class EventCreate(BaseModel):
    subject_id: str
    event_type: str
    event_time: datetime
    payload: Dict

    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("Event type must be a non-empty string")
        if not v.replace('_', '').isalnum():
            raise ValueError(
                "Event type must contain only alphanumeric characters and underscores"
            )
        return v.upper()

    @field_validator('event_time')
    @classmethod
    def validate_event_time(cls, v: datetime) -> datetime:
        if v > datetime.now(v.tzinfo):
            raise ValueError("Event time cannot be in the future")
        return v

    @field_validator('payload')
    @classmethod
    def validate_payload(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not v:
            raise ValueError("Event payload cannot be empty")
        return v

class EventResponse(BaseModel):
    id: str
    tenant_id: str
    subject_id: str
    event_type: str
    event_time: datetime
    payload: Dict[str, Any]
    hash: str
    previous_hash: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)