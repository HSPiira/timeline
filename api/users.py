from typing import Annotated
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.exc import IntegrityError

from api.deps import (
    get_user_repo,
    get_user_repo_transactional,
    get_tenant_repo,
    get_current_user,
    get_current_tenant
)
from schemas.user import UserCreate, UserUpdate, UserResponse
from schemas.token import TokenPayload
from repositories.user_repo import UserRepository
from repositories.tenant_repo import TenantRepository
from models.tenant import Tenant


router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    data: UserCreate,
    user_repo: Annotated[UserRepository, Depends(get_user_repo_transactional)],
    tenant_repo: Annotated[TenantRepository, Depends(get_tenant_repo)]
):
    """Register a new user account"""
    tenant = await tenant_repo.get_by_code(data.tenant_code)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant with code '{data.tenant_code}' not found"
        )

    if tenant.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant is not active"
        )

    try:
        user = await user_repo.create_user(
            tenant_id=tenant.id,
            username=data.username,
            email=data.email,
            password=data.password
        )
        return UserResponse.from_orm_model(user)
    except IntegrityError as e:
        if "uq_tenant_username" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{data.username}' already exists in this tenant"
            )
        elif "uq_tenant_email" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{data.email}' is already registered in this tenant"
            )
        raise


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)]
):
    """Get current authenticated user information"""
    user = await user_repo.get_by_id(current_user.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserResponse.from_orm_model(user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo_transactional)]
):
    """Update current user information"""
    user = await user_repo.get_by_id(current_user.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    try:
        if data.email:
            user.email = data.email

        if data.password:
            await user_repo.update_password(user.id, data.password)

        updated = await user_repo.update(user)
        return UserResponse.from_orm_model(updated)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email '{data.email}' is already registered in this tenant"
        )


@router.get("/", response_model=list[UserResponse])
async def list_users(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
    skip: int = 0,
    limit: int = 100
):
    """List all users in current tenant (authenticated users only)"""
    users = await user_repo.get_users_by_tenant(current_tenant.id, skip, limit)
    return [UserResponse.from_orm_model(user) for user in users]


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_current_user(
    current_user: Annotated[TokenPayload, Depends(get_current_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo_transactional)]
):
    """Deactivate current user account (soft delete)"""
    await user_repo.deactivate(current_user.sub)
