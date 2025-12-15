from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime


class UserCreate(BaseModel):
    """Schema for user registration"""
    tenant_code: str = Field(..., description="Tenant code to register under")
    username: str = Field(..., min_length=3, max_length=50, description="Unique username within tenant")
    email: EmailStr = Field(..., description="User email address (unique within tenant)")
    password: str = Field(..., min_length=8, description="User password (min 8 characters)")


class UserUpdate(BaseModel):
    """Schema for updating user information"""
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=8)


class UserResponse(BaseModel):
    """Schema for user responses (excludes password)"""
    id: str
    tenant_id: str
    username: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, user) -> "UserResponse":
        """Convert ORM model to response schema"""
        return cls(
            id=user.id,
            tenant_id=user.tenant_id,
            username=user.username,
            email=user.email,
            is_active=bool(user.is_active),
            created_at=user.created_at,
            updated_at=user.updated_at
        )
