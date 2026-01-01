"""JWT token handling for authentication."""

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from src.infrastructure.config.settings import get_settings

settings = get_settings()


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """Create JWT access token with tenant_id and user_id claims"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.algorithm
    )
    assert isinstance(encoded_jwt, str)
    return encoded_jwt


def verify_token(token: str) -> dict[str, Any]:
    """Verify and decode JWT token, returns payload"""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        if not isinstance(payload, dict):
            raise TypeError("Token payload must be a dictionary")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {str(e)}") from e
