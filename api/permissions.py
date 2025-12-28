from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_tenant, get_current_user
from core.database import get_db, get_db_transactional
from models.permission import Permission
from models.tenant import Tenant
from repositories.permission_repo import PermissionRepository
from schemas.role import PermissionCreate, PermissionResponse
from schemas.token import TokenPayload

router = APIRouter()


@router.post(
    "/", response_model=PermissionResponse, status_code=status.HTTP_201_CREATED
)
async def create_permission(
    data: PermissionCreate,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
):
    """Create a new permission (requires 'permission:create' permission)"""
    perm_repo = PermissionRepository(db)

    # Check if permission code already exists
    existing = await perm_repo.get_by_code_and_tenant(data.code, current_tenant.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Permission with code '{data.code}' already exists",
        )

    try:
        permission = Permission(
            tenant_id=current_tenant.id,
            code=data.code,
            resource=data.resource,
            action=data.action,
            description=data.description,
        )
        created = await perm_repo.create(permission)
        return PermissionResponse.model_validate(created)

    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Permission creation failed due to constraint violation",
        ) from None


@router.get("/", response_model=list[PermissionResponse])
async def list_permissions(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    resource: str = Query(None, description="Filter by resource type"),
):
    """List all permissions in current tenant (requires 'permission:read' permission)"""
    perm_repo = PermissionRepository(db)

    if resource:
        permissions = await perm_repo.get_by_resource(current_tenant.id, resource)
    else:
        permissions = await perm_repo.get_by_tenant(
            current_tenant.id, skip=skip, limit=limit
        )

    return [PermissionResponse.model_validate(perm) for perm in permissions]


@router.get("/{permission_id}", response_model=PermissionResponse)
async def get_permission(
    permission_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get permission details (requires 'permission:read' permission)"""
    perm_repo = PermissionRepository(db)

    permission = await perm_repo.get_by_id(permission_id)
    if not permission or permission.tenant_id != current_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found"
        )

    return PermissionResponse.model_validate(permission)


@router.delete("/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    permission_id: str,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
):
    """Delete permission (requires 'permission:delete' permission)"""
    perm_repo = PermissionRepository(db)

    permission = await perm_repo.get_by_id(permission_id)
    if not permission or permission.tenant_id != current_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found"
        )

    # Note: This will cascade delete all role_permission associations
    await perm_repo.delete(permission)
