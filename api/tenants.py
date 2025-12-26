from typing import Annotated
import secrets
import string
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from api.deps import get_tenant_repo, get_tenant_repo_transactional
from core.database import get_db_transactional
from schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantStatusUpdate, TenantCreateResponse
from repositories.tenant_repo import TenantRepository
from repositories.user_repo import UserRepository
from services.tenant_initialization_service import TenantInitializationService
from core.enums import TenantStatus


router = APIRouter()


def generate_secure_password(length: int = 16) -> str:
    """
    Generate a cryptographically secure random password.

    Uses secrets module for cryptographic randomness.
    Password contains uppercase, lowercase, digits, and special characters.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password


@router.post("/", response_model=TenantCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    db: Annotated[AsyncSession, Depends(get_db_transactional)]
):
    """
    Create a new tenant with an admin user in a single transaction.

    Uses atomic database constraint for race-free uniqueness checking.
    Returns tenant details along with admin credentials.
    """
    from models.tenant import Tenant

    tenant = Tenant(
        code=data.code,
        name=data.name,
        status=TenantStatus.ACTIVE.value  # Always create tenants as ACTIVE
    )

    try:
        # Create repositories and services from the same transactional session
        tenant_repo = TenantRepository(db)
        user_repo = UserRepository(db)
        init_service = TenantInitializationService(db)

        # Create tenant
        created = await tenant_repo.create(tenant)

        # Create admin user for the new tenant in the same transaction
        admin_username = "admin"
        admin_password = "admin@123"
        # admin_password = generate_secure_password()  # Cryptographically secure random password
        admin_email = f"admin@{data.code}.tl"

        admin_user = await user_repo.create_user(
            tenant_id=created.id,
            username=admin_username,
            email=admin_email,
            password=admin_password
        )

        # Initialize RBAC: create permissions, roles, and assign admin role
        await init_service.initialize_tenant(
            tenant_id=created.id,
            admin_user_id=admin_user.id
        )

        return TenantCreateResponse(
            tenant=TenantResponse.model_validate(created),
            admin_username=admin_username,
            admin_password=admin_password
        )
    except IntegrityError:
        # Database constraint violation 
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
