from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Any, Dict


class EventSchemaCreate(BaseModel):
    """Schema for creating an event schema"""
    event_type: str
    schema_json: Dict[str, Any]
    version: int

    @field_validator('event_type')
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("Event type must be a non-empty string")
        if not v.replace('_', '').isalnum():
            raise ValueError(
                "Event type must contain only alphanumeric characters and underscores"
            )
        return v.lower()

    @field_validator('version')
    @classmethod
    def validate_version(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Schema version must be >= 1")
        return v

    @field_validator('schema_json')
    @classmethod
    def validate_schema_json(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not v:
            raise ValueError("Schema JSON cannot be empty")
        if 'type' not in v:
            raise ValueError("Schema must have a 'type' field (JSON Schema requirement)")
        return v


class EventSchemaUpdate(BaseModel):
    """Schema for updating an event schema"""
    is_active: bool | None = None


class EventSchemaResponse(BaseModel):
    """Schema for event schema responses"""
    id: str
    tenant_id: str
    event_type: str
    schema_json: Dict[str, Any]
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
