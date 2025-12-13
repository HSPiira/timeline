from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional


class TenantCreate(BaseModel):
    """Schema for creating a tenant"""
    code: str
    name: str
    status: str = "active"

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

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = {"active", "suspended", "archived"}
        if v not in valid_statuses:
            raise ValueError(
                f"Tenant status must be one of: {', '.join(valid_statuses)}"
            )
        return v


class TenantUpdate(BaseModel):
    """Schema for updating a tenant"""
    name: Optional[str] = None
    status: Optional[str] = None

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid_statuses = {"active", "suspended", "archived"}
            if v not in valid_statuses:
                raise ValueError(
                    f"Tenant status must be one of: {', '.join(valid_statuses)}"
                )
        return v


class TenantResponse(BaseModel):
    """Schema for tenant responses"""
    id: str
    code: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
