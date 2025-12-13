from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional
from core.enums import TenantStatus


class TenantCreate(BaseModel):
    """Schema for creating a tenant"""
    code: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE

    @field_validator('code')
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("Tenant code must be a non-empty string")
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError(
                "Tenant code must contain only alphanumeric characters, hyphens, and underscores"
            )
        return v.lower()


class TenantUpdate(BaseModel):
    """Schema for updating a tenant"""
    name: Optional[str] = None
    status: Optional[TenantStatus] = None


class TenantResponse(BaseModel):
    """Schema for tenant responses"""
    id: str
    code: str
    name: str
    status: TenantStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
