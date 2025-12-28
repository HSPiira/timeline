from datetime import datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from core.config import get_settings

settings = get_settings()


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """Create JWT access token with tenant_id and user_id claims"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
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
            raise ValueError("Token payload must be a dictionary")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {str(e)}") from e


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        result = bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
        assert isinstance(result, bool)
        return result
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    result = hashed.decode("utf-8")
    assert isinstance(result, str)
    return result
