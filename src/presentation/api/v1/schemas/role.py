from datetime import datetime

from pydantic import BaseModel, Field


# Role Schemas
class RoleBase(BaseModel):
    """Base role schema"""

    code: str = Field(..., min_length=1, max_length=100, description="Unique role code")
    name: str = Field(..., min_length=1, max_length=255, description="Display name")
    description: str | None = Field(None, description="Role description")


class RoleCreate(RoleBase):
    """Schema for creating a role"""

    permission_codes: list[str] = Field(
        default_factory=list,
        description="List of permission codes to assign to this role",
    )


class RoleUpdate(BaseModel):
    """Schema for updating a role"""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None


class RoleResponse(RoleBase):
    """Schema for role response"""

    id: str
    tenant_id: str
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoleWithPermissions(RoleResponse):
    """Role response with permissions included"""

    permissions: list["PermissionResponse"] = []

    class Config:
        from_attributes = True


# Permission Schemas
class PermissionBase(BaseModel):
    """Base permission schema"""

    code: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Permission code (e.g., 'event:create')",
    )
    resource: str = Field(
        ..., min_length=1, max_length=100, description="Resource name (e.g., 'event')"
    )
    action: str = Field(
        ..., min_length=1, max_length=100, description="Action name (e.g., 'create')"
    )
    description: str | None = Field(None, description="Permission description")


class PermissionCreate(PermissionBase):
    """Schema for creating a permission"""

    pass


class PermissionResponse(PermissionBase):
    """Schema for permission response"""

    id: str
    tenant_id: str

    class Config:
        from_attributes = True


# User-Role Assignment Schemas
class UserRoleAssign(BaseModel):
    """Schema for assigning a role to a user"""

    role_id: str = Field(..., description="Role ID to assign")
    expires_at: datetime | None = Field(None, description="Optional expiration time")


class UserRoleResponse(BaseModel):
    """Schema for user-role assignment response"""

    id: str
    user_id: str
    role_id: str
    tenant_id: str
    assigned_by: str | None
    assigned_at: datetime
    expires_at: datetime | None

    class Config:
        from_attributes = True


# Role-Permission Assignment Schemas
class RolePermissionAssign(BaseModel):
    """Schema for assigning permissions to a role"""

    permission_ids: list[str] = Field(..., description="List of permission IDs to assign")


class RolePermissionResponse(BaseModel):
    """Schema for role-permission assignment response"""

    id: str
    role_id: str
    permission_id: str
    tenant_id: str

    class Config:
        from_attributes = True


# Forward reference resolution
RoleWithPermissions.model_rebuild()
