import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import TenantStatus
from src.infrastructure.config.settings import get_settings
from src.infrastructure.persistence.database import get_db
from src.infrastructure.persistence.repositories import (
    TenantRepository,
    UserRepository,
)
from src.infrastructure.security.jwt import create_access_token
from src.presentation.api.v1.schemas.token import Token, TokenRequest
from src.presentation.middleware.rate_limit import limiter

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/token", response_model=Token)
@limiter.limit("5/minute")  # Limit login attempts to 5 per minute per IP
async def login(
    request: Request,  # Required by slowapi for rate limiting (extracts remote address)
    token_request: TokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Generate JWT access token for authenticated user.

    Rate limit: 5 requests per minute per IP

    Token contains:
    - sub: user_id (subject)
    - tenant_id: tenant the user belongs to
    - exp: expiration timestamp

    This prevents tenant isolation bypass via header spoofing.
    """
    # Verify tenant exists and is active
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_code(token_request.tenant_code)

    if not tenant or tenant.status != TenantStatus.ACTIVE.value:
        # Use generic error to prevent tenant enumeration
        logger.warning("Login attempt for invalid/inactive tenant: %s", token_request.tenant_code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Authenticate user with username, tenant, and password
    user_repo = UserRepository(db)
    user = await user_repo.authenticate(
        username=token_request.username,
        tenant_id=tenant.id,
        password=token_request.password,
    )

    if not user:
        logger.warning(
            "Failed login attempt for user: %s in tenant: %s",
            token_request.username,
            tenant.id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create JWT token with enhanced claims
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={
            "sub": user.id,  # User ID (subject)
            "tenant_id": tenant.id,  # Tenant ID claim - prevents spoofing
            "username": user.username,  # Add username for logging
            "iat": datetime.now(UTC),  # Issued at timestamp
        },
        expires_delta=access_token_expires,
    )

    logger.info("Successful login for user: %s in tenant: %s", user.username, tenant.id)
    return Token(access_token=access_token, token_type="bearer")


# Properly secured test endpoint - only in development with additional security
if settings.debug and os.getenv("ENABLE_TEST_AUTH") == "true":

    @router.post("/token/test", response_model=Token, include_in_schema=False)
    @limiter.limit("10/hour")  # Add rate limiting even for test
    async def create_test_token(
        request: Request,
        tenant_id: str,
        user_id: str = "test_user",
        test_key: str = None,
    ):
        """Development-only test token generator with additional security."""

        # Verify test key
        expected_key = os.getenv("TEST_AUTH_KEY")
        if not expected_key or test_key != expected_key:
            logger.warning("Invalid test token request from %s", request.client.host)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        access_token = create_access_token(
            data={
                "sub": user_id,
                "tenant_id": tenant_id,
                "test_token": True,  # Mark as test token
                "iat": datetime.now(UTC),
            }
        )

        logger.info("Test token created for tenant: %s, user: %s", tenant_id, user_id)
        return Token(access_token=access_token, token_type="bearer")
