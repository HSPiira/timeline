"""Test health check endpoint"""

import pytest


@pytest.mark.asyncio
async def test_health_check_healthy(client):
    """Test health check returns healthy status"""
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"]["api"] is True
    assert data["checks"]["database"] is True


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Test root endpoint returns app info"""
    response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Timeline"
    assert "version" in data
    assert data["status"] == "running"
