from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from src.application.services.tenant_creation_service import TenantCreationService
from src.domain.enums import TenantStatus
from src.infrastructure.persistence.repositories.tenant_repo import TenantRepository
from src.presentation.api.dependencies import (
    get_tenant_creation_service,
    get_tenant_repo,
    get_tenant_repo_transactional,
)
from src.presentation.api.v1.schemas.tenant import (
    TenantCreate,
    TenantCreateResponse,
    TenantResponse,
    TenantStatusUpdate,
    TenantUpdate,
)

router = APIRouter()


@router.post("/", response_model=TenantCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    service: Annotated[TenantCreationService, Depends(get_tenant_creation_service)],
):
    """
    Create a new tenant with an admin user in a single transaction.

    Uses atomic database constraint for race-free uniqueness checking.
    Returns tenant details along with admin credentials.
    """
    try:
        result = await service.create_tenant(code=data.code, name=data.name)

        return TenantCreateResponse(
            tenant=TenantResponse.model_validate(result.tenant),
            admin_username=result.admin_username,
            admin_password=result.admin_password,
        )
    except IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant with code '{data.code}' already exists",
        ) from e


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, repo: Annotated[TenantRepository, Depends(get_tenant_repo)]):
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
    active_only: bool = False,
):
    """List all tenants with optional filtering by status"""
    if active_only:
        return await repo.get_active_tenants(skip, limit)

    return await repo.get_all(skip, limit)


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    data: TenantUpdate,
    repo: Annotated[TenantRepository, Depends(get_tenant_repo_transactional)],
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
    repo: Annotated[TenantRepository, Depends(get_tenant_repo_transactional)],
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
    repo: Annotated[TenantRepository, Depends(get_tenant_repo_transactional)],
):
    """Delete a tenant (soft delete by archiving)"""
    updated = await repo.update_status(tenant_id, TenantStatus.ARCHIVED)

    if not updated:
        raise HTTPException(status_code=404, detail="Tenant not found")
