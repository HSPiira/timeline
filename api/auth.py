from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.auth import create_access_token
from core.config import get_settings
from core.database import get_db
from repositories.tenant_repo import TenantRepository
from repositories.user_repo import UserRepository
from schemas.token import Token, TokenRequest

router = APIRouter()
settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


@router.post("/token", response_model=Token)
@limiter.limit("5/minute")  # Limit login attempts to 5 per minute per IP
async def login(
    request_obj: Request,  # Required for slowapi
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

    # Authenticate user with username, tenant, and password
    user = await UserRepository(db).authenticate(
        username=request.username,
        tenant_id=tenant.id,
        password=request.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create JWT token with tenant_id claim
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={
            "sub": user.id,            # User ID (subject)
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
