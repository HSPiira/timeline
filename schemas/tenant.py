from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional
from core.enums import TenantStatus


class TenantCreate(BaseModel):
    """Schema for creating a tenant"""
    code: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE


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
