from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import create_access_token
from core.config import get_settings
from core.database import get_db
from repositories.tenant_repo import TenantRepository
from schemas.token import Token, TokenRequest

router = APIRouter()
settings = get_settings()


@router.post("/token", response_model=Token)
async def login(
    request: TokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Generate JWT access token for authenticated user.

    Token contains:
    - sub: user_id (subject)
    - tenant_id: tenant the user belongs to
    - exp: expiration timestamp

    This prevents tenant isolation bypass via header spoofing.
    """
    # Verify tenant exists and is active
    tenant = await TenantRepository(db).get_by_code(request.tenant_code)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if tenant.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant account is not active"
        )

    # TODO: Validate username/password against user database
    # For now, this is a simplified implementation that only validates tenant
    # In production, you should:
    # 1. Look up user by username
    # 2. Verify user belongs to the tenant
    # 3. Verify password hash
    # 4. Check user is active/enabled

    # Create JWT token with tenant_id claim
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={
            "sub": request.username,  # User ID (subject)
            "tenant_id": tenant.id     # Tenant ID claim - prevents spoofing
        },
        expires_delta=access_token_expires
    )

    return Token(access_token=access_token, token_type="bearer")


@router.post("/token/test", response_model=Token, include_in_schema=False)
async def create_test_token(
    tenant_id: str,
    user_id: str = "test_user"
):
    """
    Development-only endpoint to generate test tokens.
    Remove or disable in production.
    """
    access_token = create_access_token(
        data={
            "sub": user_id,
            "tenant_id": tenant_id
        }
    )
    return Token(access_token=access_token, token_type="bearer")
