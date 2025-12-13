from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional


class SubjectCreate(BaseModel):
    """Schema for creating a subject"""
    subject_type: str
    external_ref: Optional[str] = None

    @field_validator('subject_type')
    @classmethod
    def validate_subject_type(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("Subject type must be a non-empty string")
        if not v.replace('_', '').isalnum():
            raise ValueError(
                "Subject type must contain only alphanumeric characters and underscores"
            )
        return v.upper()


class SubjectUpdate(BaseModel):
    """Schema for updating a subject"""
    external_ref: Optional[str] = None


class SubjectResponse(BaseModel):
    """Schema for subject responses"""
    id: str
    tenant_id: str
    subject_type: str
    external_ref: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
