"""Tests for Redis cache service"""

from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as redis

from src.infrastructure.cache.redis_cache import CacheService


@pytest.fixture
async def cache_service():
    """Create cache service with mock Redis client"""
    service = CacheService()
    # Mock Redis client
    service.redis = AsyncMock()
    service._connected = True
    return service


@pytest.fixture
async def disconnected_cache():
    """Create disconnected cache service"""
    service = CacheService()
    service.redis = None
    service._connected = False
    return service


@pytest.mark.asyncio
async def test_cache_get_hit(cache_service):
    """Test cache get when key exists"""
    # Mock Redis to return serialized data
    cache_service.redis.get = AsyncMock(return_value='{"user_id": "123", "name": "Test User"}')

    result = await cache_service.get("test_key")

    assert result is not None
    assert result["user_id"] == "123"
    assert result["name"] == "Test User"
    cache_service.redis.get.assert_called_once_with("test_key")


@pytest.mark.asyncio
async def test_cache_get_miss(cache_service):
    """Test cache get when key doesn't exist"""
    cache_service.redis.get = AsyncMock(return_value=None)

    result = await cache_service.get("missing_key")

    assert result is None
    cache_service.redis.get.assert_called_once_with("missing_key")


@pytest.mark.asyncio
async def test_cache_set_success(cache_service):
    """Test successful cache set"""
    cache_service.redis.setex = AsyncMock()

    data = {"user_id": "456", "email": "test@example.com"}
    result = await cache_service.set("user:456", data, ttl=300)

    assert result is True
    cache_service.redis.setex.assert_called_once()

    # Verify arguments
    call_args = cache_service.redis.setex.call_args
    assert call_args[0][0] == "user:456"  # key
    assert call_args[0][1] == 300  # ttl
    # Third arg is JSON string - verify it deserializes correctly
    import json

    assert json.loads(call_args[0][2]) == data


@pytest.mark.asyncio
async def test_cache_delete_success(cache_service):
    """Test successful cache delete"""
    cache_service.redis.delete = AsyncMock()

    result = await cache_service.delete("test_key")

    assert result is True
    cache_service.redis.delete.assert_called_once_with("test_key")


@pytest.mark.asyncio
async def test_cache_delete_pattern(cache_service):
    """Test delete pattern (wildcard deletion)"""

    # Mock scan_iter to return matching keys
    async def mock_scan_iter(match=None):
        keys = [
            "permissions:tenant-1:user-1",
            "permissions:tenant-1:user-2",
            "permissions:tenant-1:user-3",
        ]
        for key in keys:
            yield key

    cache_service.redis.scan_iter = mock_scan_iter
    cache_service.redis.delete = AsyncMock()

    deleted_count = await cache_service.delete_pattern("permissions:tenant-1:*")

    assert deleted_count == 3
    assert cache_service.redis.delete.call_count == 3


@pytest.mark.asyncio
async def test_cache_clear_all(cache_service):
    """Test clearing entire cache"""
    cache_service.redis.flushdb = AsyncMock()

    result = await cache_service.clear_all()

    assert result is True
    cache_service.redis.flushdb.assert_called_once()


@pytest.mark.asyncio
async def test_cache_unavailable_returns_none(disconnected_cache):
    """Test that unavailable cache returns None for get"""
    result = await disconnected_cache.get("any_key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_unavailable_set_returns_false(disconnected_cache):
    """Test that unavailable cache returns False for set"""
    result = await disconnected_cache.set("any_key", {"data": "value"})
    assert result is False


@pytest.mark.asyncio
async def test_cache_is_available(cache_service):
    """Test cache availability check"""
    assert cache_service.is_available() is True


@pytest.mark.asyncio
async def test_cache_is_not_available(disconnected_cache):
    """Test cache unavailability check"""
    assert disconnected_cache.is_available() is False


@pytest.mark.asyncio
async def test_cache_connect_success():
    """Test successful cache connection"""
    with patch("redis.asyncio.Redis") as mock_redis_class:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_redis_class.return_value = mock_client

        cache = CacheService()
        await cache.connect()

        assert cache.is_available() is True
        mock_client.ping.assert_called_once()


@pytest.mark.asyncio
async def test_cache_connect_failure():
    """Test cache connection failure"""
    with patch("redis.asyncio.Redis") as mock_redis_class:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=redis.ConnectionError("Connection refused"))
        mock_redis_class.return_value = mock_client

        cache = CacheService()
        await cache.connect()

        # Should gracefully handle failure
        assert cache.is_available() is False
        assert cache.redis is None


@pytest.mark.asyncio
async def test_cache_disconnect(cache_service):
    """Test cache disconnection"""
    cache_service.redis.close = AsyncMock()

    await cache_service.disconnect()

    cache_service.redis.close.assert_called_once()
    assert cache_service.is_available() is False


@pytest.mark.asyncio
async def test_cache_error_handling_on_get(cache_service):
    """Test error handling when get fails"""
    cache_service.redis.get = AsyncMock(side_effect=Exception("Redis error"))

    result = await cache_service.get("test_key")

    # Should return None on error, not raise
    assert result is None


@pytest.mark.asyncio
async def test_cache_error_handling_on_set(cache_service):
    """Test error handling when set fails"""
    cache_service.redis.setex = AsyncMock(side_effect=Exception("Redis error"))

    result = await cache_service.set("test_key", {"data": "value"})

    # Should return False on error, not raise
    assert result is False


@pytest.mark.asyncio
async def test_cache_with_complex_data(cache_service):
    """Test caching complex nested data structures"""
    cache_service.redis.get = AsyncMock(return_value=None)
    cache_service.redis.setex = AsyncMock()

    complex_data = {
        "tenant_id": "tenant-123",
        "permissions": ["event:create", "subject:read", "event:delete"],
        "metadata": {"roles": ["admin", "editor"], "expires_at": None},
        "count": 42,
    }

    # Set complex data
    result = await cache_service.set("complex_key", complex_data, ttl=600)
    assert result is True

    # Verify it was serialized correctly
    call_args = cache_service.redis.setex.call_args[0]
    import json

    stored_data = json.loads(call_args[2])
    assert stored_data == complex_data


@pytest.mark.asyncio
async def test_cache_ttl_values(cache_service):
    """Test different TTL values"""
    cache_service.redis.setex = AsyncMock()

    # Test default TTL
    await cache_service.set("key1", {"data": 1})
    assert cache_service.redis.setex.call_args[0][1] == 300  # Default 300s

    # Test custom TTL
    await cache_service.set("key2", {"data": 2}, ttl=900)
    assert cache_service.redis.setex.call_args[0][1] == 900

    # Test short TTL
    await cache_service.set("key3", {"data": 3}, ttl=60)
    assert cache_service.redis.setex.call_args[0][1] == 60
