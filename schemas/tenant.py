from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from core.enums import TenantStatus
from domain.value_objects import TenantCode


class TenantCreate(BaseModel):
    """Schema for creating a tenant - status is always ACTIVE by default"""

    code: str
    name: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        """Validate tenant code using TenantCode value object"""
        TenantCode(value=v)  # Raises ValueError if invalid
        return v


class TenantUpdate(BaseModel):
    """Schema for updating a tenant"""

    name: str | None = None
    status: TenantStatus | None = None


class TenantStatusUpdate(BaseModel):
    """Schema for updating tenant status"""

    new_status: TenantStatus


class TenantResponse(BaseModel):
    """Schema for tenant responses"""

    id: str
    code: str
    name: str
    status: TenantStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantCreateResponse(BaseModel):
    """Schema for tenant creation response with admin credentials"""

    tenant: TenantResponse
    admin_username: str
    admin_password: str

    model_config = ConfigDict(from_attributes=True)
