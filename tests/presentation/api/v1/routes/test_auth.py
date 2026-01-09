"""Test authentication endpoints"""

import pytest
from fastapi import status


@pytest.mark.asyncio
async def test_login_success(client, test_tenant, test_user):
    """Test successful login"""
    response = await client.post(
        "/auth/token",
        json={
            "tenant_code": test_tenant.code,
            "username": test_user.username,
            "password": "testpass123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client, test_tenant):
    """Test login with invalid credentials"""
    response = await client.post(
        "/auth/token",
        json={"tenant_code": test_tenant.code, "username": "testuser", "password": "wrongpassword"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_login_invalid_tenant(client):
    """Test login with non-existent tenant"""
    response = await client.post(
        "/auth/token",
        json={"tenant_code": "NONEXISTENT", "username": "testuser", "password": "testpass123"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_rate_limiting_login(client, test_tenant, test_user):
    """Test that login endpoint is rate limited"""
    # Make 6 failed login attempts (rate limit is 5/minute)
    for i in range(6):
        response = await client.post(
            "/auth/token",
            json={
                "tenant_code": test_tenant.code,
                "username": test_user.username,
                "password": "wrongpassword",
            },
        )

        if i < 5:
            # First 5 should return 401 (invalid credentials)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
        else:
            # 6th should be rate limited
            assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
