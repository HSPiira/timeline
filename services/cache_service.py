"""Redis-based caching service for performance optimization"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

import redis.asyncio as redis

from core.config import get_settings

logger = logging.getLogger(__name__)


class CacheService:
    """
    Async Redis cache service with TTL support

    Provides high-performance caching for:
    - Authorization permissions (5 min TTL)
    - Event schemas (10 min TTL)
    - Tenant lookups (15 min TTL)

    Expected performance improvement: 90% reduction in repeated queries
    """

    def __init__(self, redis_client: redis.Redis | None = None):
        """
        Initialize cache service

        Args:
            redis_client: Optional Redis client (for testing/DI)
        """
        self.redis = redis_client
        self.settings = get_settings()
        self._connected = False

    async def connect(self):
        """Establish Redis connection (call on app startup)"""
        if self.redis is None:
            try:
                self.redis = redis.Redis(
                    host=self.settings.redis_host,
                    port=self.settings.redis_port,
                    db=self.settings.redis_db,
                    password=self.settings.redis_password
                    if self.settings.redis_password
                    else None,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )
                # Test connection
                await self.redis.ping()
                self._connected = True
                logger.info(
                    f"Redis cache connected: {self.settings.redis_host}:{self.settings.redis_port}"
                )
            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(
                    f"Redis connection failed: {e}. Cache disabled - falling back to database queries."
                )
                self._connected = False
                self.redis = None

    async def disconnect(self):
        """Close Redis connection (call on app shutdown)"""
        if self.redis:
            await self.redis.close()
            self._connected = False
            logger.info("Redis cache disconnected")

    def is_available(self) -> bool:
        """Check if Redis is connected and available"""
        return self._connected and self.redis is not None

    async def get(self, key: str) -> Any | None:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value (deserialized from JSON) or None if not found/unavailable
        """
        if not self.is_available() or self.redis is None:
            return None

        redis_client = self.redis  # Local variable for type narrowing
        try:
            value = await redis_client.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            logger.debug(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set value in cache with TTL

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time-to-live in seconds (default: 300 = 5 minutes)

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available() or self.redis is None:
            return False

        redis_client = self.redis  # Local variable for type narrowing
        try:
            serialized = json.dumps(value)
            await redis_client.setex(key, ttl, serialized)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache

        Args:
            key: Cache key to delete

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available() or self.redis is None:
            return False

        redis_client = self.redis  # Local variable for type narrowing
        try:
            await redis_client.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern

        Args:
            pattern: Redis pattern (e.g., "permissions:tenant-123:*")

        Returns:
            Number of keys deleted
        """
        if not self.is_available() or self.redis is None:
            return 0

        redis_client = self.redis  # Local variable for type narrowing
        try:
            # Scan for matching keys (cursor-based for large datasets)
            deleted = 0
            async for key in redis_client.scan_iter(match=pattern):
                await redis_client.delete(key)
                deleted += 1

            if deleted > 0:
                logger.info(f"Cache INVALIDATE: {pattern} ({deleted} keys deleted)")
            return deleted
        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return 0

    async def clear_all(self) -> bool:
        """
        Clear entire cache (use with caution!)

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available() or self.redis is None:
            return False

        redis_client = self.redis  # Local variable for type narrowing
        try:
            await redis_client.flushdb()
            logger.warning("Cache CLEARED: All keys deleted")
            return True
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return False


def cached(key_prefix: str, ttl: int = 300, key_builder: Callable | None = None):
    """
    Decorator for caching async function results

    Args:
        key_prefix: Prefix for cache key (e.g., "permissions")
        ttl: Time-to-live in seconds
        key_builder: Optional function to build cache key from args
                    If None, uses all args/kwargs as key components

    Example:
        @cached(key_prefix="permissions", ttl=300)
        async def get_user_permissions(cache: CacheService, user_id: str, tenant_id: str):
            # Cache key will be: permissions:user_id:tenant_id
            return await fetch_from_db(user_id, tenant_id)
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract cache service (assume first arg or 'cache' kwarg)
            cache: CacheService | None = None

            # Try to find cache service in args/kwargs
            if args and isinstance(args[0], CacheService):
                cache = args[0]
                func_args = args[1:]
            elif "cache" in kwargs:
                cache = kwargs["cache"]
                func_args = args
            else:
                # No cache service found - execute without caching
                return await func(*args, **kwargs)

            # Type narrowing: ensure cache is not None
            if cache is None:
                return await func(*args, **kwargs)

            # Build cache key
            if key_builder:
                cache_key = key_builder(*func_args, **kwargs)
            else:
                # Default: combine prefix with all args/kwargs
                key_parts = [str(arg) for arg in func_args]
                key_parts.extend(
                    f"{k}={v}" for k, v in sorted(kwargs.items()) if k != "cache"
                )
                cache_key = f"{key_prefix}:{':'.join(key_parts)}"

            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            await cache.set(cache_key, result, ttl=ttl)

            return result

        return wrapper

    return decorator
