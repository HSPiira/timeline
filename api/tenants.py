from typing import Annotated
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.exc import IntegrityError
from api.deps import get_tenant_repo, get_tenant_repo_transactional
from schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantStatusUpdate
from repositories.tenant_repo import TenantRepository
from core.enums import TenantStatus


router = APIRouter()


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    repo: Annotated[TenantRepository, Depends(get_tenant_repo_transactional)]
):
    """
    Create a new tenant.

    Uses atomic database constraint for race-free uniqueness checking.
    """
    from models.tenant import Tenant

    tenant = Tenant(
        code=data.code,
        name=data.name,
        status=data.status.value  # Store enum value, not enum object
    )

    try:
        created = await repo.create(tenant)
        return created
    except IntegrityError:
        # Database constraint violation (duplicate code)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant with code '{data.code}' already exists"
        )


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    repo: Annotated[TenantRepository, Depends(get_tenant_repo)]
):
    """Get a tenant by ID"""
    tenant = await repo.get_by_id(tenant_id)

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenant


@router.get("/", response_model=list[TenantResponse])
async def list_tenants(
    repo: Annotated[TenantRepository, Depends(get_tenant_repo)],
    skip: int = 0,
    limit: int = 100,
    *,
    active_only: bool = False
):
    """List all tenants with optional filtering by status"""
    if active_only:
        return await repo.get_active_tenants(skip, limit)

    return await repo.get_all(skip, limit)


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    data: TenantUpdate,
    repo: Annotated[TenantRepository, Depends(get_tenant_repo_transactional)]
):
    """Update a tenant"""
    tenant = await repo.get_by_id(tenant_id)

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if data.name is not None:
        tenant.name = data.name

    if data.status is not None:
        tenant.status = data.status.value

    updated = await repo.update(tenant)
    return updated


@router.patch("/{tenant_id}/status", response_model=TenantResponse)
async def update_tenant_status(
    tenant_id: str,
    data: TenantStatusUpdate,
    repo: Annotated[TenantRepository, Depends(get_tenant_repo_transactional)]
):
    """
    Update tenant status (activate, suspend, archive).

    Request body: {"new_status": "active"|"suspended"|"archived"}
    """
    updated = await repo.update_status(tenant_id, data.new_status)

    if not updated:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return updated


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: str,
    repo: Annotated[TenantRepository, Depends(get_tenant_repo_transactional)]
):
    """Delete a tenant (soft delete by archiving)"""
    updated = await repo.update_status(tenant_id, TenantStatus.ARCHIVED)

    if not updated:
        raise HTTPException(status_code=404, detail="Tenant not found")
