from typing import Annotated, List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.exc import IntegrityError

from api.deps import get_current_user, get_current_tenant, require_permission
from schemas.token import TokenPayload
from schemas.role import UserRoleAssign, RoleResponse
from models.tenant import Tenant
from repositories.permission_repo import PermissionRepository
from repositories.role_repo import RoleRepository
from core.database import get_db_transactional, get_db
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


@router.post("/users/{user_id}/roles", status_code=status.HTTP_201_CREATED)
async def assign_role_to_user(
    user_id: str,
    data: UserRoleAssign,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
    _: Annotated[TokenPayload, Depends(require_permission("role", "assign"))]
):
    """Assign role to user (requires 'role:assign' permission)"""
    role_repo = RoleRepository(db)
    perm_repo = PermissionRepository(db)

    # Verify role exists and belongs to tenant
    role = await role_repo.get_by_id(data.role_id)
    if not role or role.tenant_id != current_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    if not role.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign inactive role"
        )

    try:
        user_role = await perm_repo.assign_role_to_user(
            user_id=user_id,
            role_id=data.role_id,
            tenant_id=current_tenant.id,
            assigned_by=current_user.sub
        )

        # If expires_at provided, update it
        if data.expires_at:
            user_role.expires_at = data.expires_at
            await db.flush()

        return {
            "message": "Role assigned successfully",
            "user_id": user_id,
            "role_id": data.role_id
        }

    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has this role assigned"
        ) from None


@router.delete("/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_from_user(
    user_id: str,
    role_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
    _: Annotated[TokenPayload, Depends(require_permission("role", "assign"))] 
):
    """Remove role from user (requires 'role:assign' permission)"""
    perm_repo = PermissionRepository(db)
    role_repo = RoleRepository(db)

    # Verify role exists and belongs to tenant
    role = await role_repo.get_by_id(role_id)
    if not role or role.tenant_id != current_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    success = await perm_repo.remove_role_from_user(user_id, role_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role assignment not found"
        )


@router.get("/users/me/roles", response_model=List[RoleResponse])
async def get_my_roles(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get roles assigned to current user"""
    perm_repo = PermissionRepository(db)

    roles = await perm_repo.get_user_roles(current_user.sub, current_tenant.id)
    return [RoleResponse.model_validate(role) for role in roles]


@router.get("/users/{user_id}/roles", response_model=List[RoleResponse])
async def get_user_roles(
    user_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[TokenPayload, Depends(require_permission("role", "read"))]
):
    """Get all roles assigned to a user (requires 'role:read' permission)"""
    perm_repo = PermissionRepository(db)

    roles = await perm_repo.get_user_roles(user_id, current_tenant.id)
    return [RoleResponse.model_validate(role) for role in roles]
