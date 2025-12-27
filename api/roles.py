from typing import Annotated, List
from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from api.deps import get_current_user, get_current_tenant
from schemas.token import TokenPayload
from schemas.role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleWithPermissions,
    UserRoleAssign,
    UserRoleResponse,
    RolePermissionAssign
)
from models.tenant import Tenant
from models.role import Role
from repositories.role_repo import RoleRepository
from repositories.permission_repo import PermissionRepository
from core.database import get_db_transactional, get_db
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    data: RoleCreate,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)]
):
    """Create a new role (requires 'role:create' permission)"""
    role_repo = RoleRepository(db)
    perm_repo = PermissionRepository(db)

    # Check if role code already exists
    existing = await role_repo.get_by_code_and_tenant(data.code, current_tenant.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role with code '{data.code}' already exists"
        )

    try:
        # Create the role
        role = Role(
            tenant_id=current_tenant.id,
            code=data.code,
            name=data.name,
            description=data.description,
            is_system=False,
            is_active=True
        )
        created_role = await role_repo.create(role)

        # Assign permissions if provided
        if data.permission_codes:
            for perm_code in data.permission_codes:
                permission = await perm_repo.get_by_code_and_tenant(perm_code, current_tenant.id)
                if permission:
                    await perm_repo.assign_permission_to_role(
                        role_id=created_role.id,
                        permission_id=permission.id,
                        tenant_id=current_tenant.id
                    )

        return RoleResponse.model_validate(created_role)

    except IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role creation failed due to constraint violation"
        ) from None


@router.get("/", response_model=List[RoleResponse])
async def list_roles(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    include_inactive: bool = Query(False)
):
    """List all roles in current tenant (requires 'role:read' permission)"""
    role_repo = RoleRepository(db)
    roles = await role_repo.get_by_tenant(
        current_tenant.id,
        skip=skip,
        limit=limit,
        include_inactive=include_inactive
    )
    return [RoleResponse.model_validate(role) for role in roles]


@router.get("/{role_id}", response_model=RoleWithPermissions)
async def get_role(
    role_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get role details with permissions (requires 'role:read' permission)"""
    role_repo = RoleRepository(db)
    perm_repo = PermissionRepository(db)

    role = await role_repo.get_by_id(role_id)
    if not role or role.tenant_id != current_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Get permissions for this role
    permissions = await perm_repo.get_permissions_for_role(role_id, current_tenant.id)

    role_dict = {
        "id": role.id,
        "tenant_id": role.tenant_id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "is_active": role.is_active,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
        "permissions": permissions
    }

    return RoleWithPermissions.model_validate(role_dict)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: str,
    data: RoleUpdate,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)]
):
    """Update role details (requires 'role:update' permission)"""
    role_repo = RoleRepository(db)

    role = await role_repo.get_by_id(role_id)
    if not role or role.tenant_id != current_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Prevent modification of system roles
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify system roles"
        )

    # Update fields
    if data.name is not None:
        role.name = data.name
    if data.description is not None:
        role.description = data.description
    if data.is_active is not None:
        role.is_active = data.is_active

    updated_role = await role_repo.update(role)
    return RoleResponse.model_validate(updated_role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)]
):
    """Deactivate role (soft delete) (requires 'role:delete' permission)"""
    role_repo = RoleRepository(db)

    role = await role_repo.get_by_id(role_id)
    if not role or role.tenant_id != current_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Prevent deletion of system roles
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system roles"
        )

    await role_repo.deactivate(role_id)


@router.post("/{role_id}/permissions", status_code=status.HTTP_201_CREATED)
async def assign_permissions_to_role(
    role_id: str,
    data: RolePermissionAssign,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)]
):
    """Assign permissions to role (requires 'role:update' permission)"""
    role_repo = RoleRepository(db)
    perm_repo = PermissionRepository(db)

    role = await role_repo.get_by_id(role_id)
    if not role or role.tenant_id != current_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    # Assign each permission
    for permission_id in data.permission_ids:
        permission = await perm_repo.get_by_id(permission_id)
        if not permission or permission.tenant_id != current_tenant.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Permission {permission_id} not found"
            )

        try:
            await perm_repo.assign_permission_to_role(
                role_id=role_id,
                permission_id=permission_id,
                tenant_id=current_tenant.id
            )
        except IntegrityError:
            # Permission already assigned, skip
            pass

    return {"message": "Permissions assigned successfully"}


@router.delete("/{role_id}/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_permission_from_role(
    role_id: str,
    permission_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)]
):
    """Remove permission from role (requires 'role:update' permission)"""
    role_repo = RoleRepository(db)
    perm_repo = PermissionRepository(db)

    role = await role_repo.get_by_id(role_id)
    if not role or role.tenant_id != current_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    success = await perm_repo.remove_permission_from_role(role_id, permission_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission assignment not found"
        )
