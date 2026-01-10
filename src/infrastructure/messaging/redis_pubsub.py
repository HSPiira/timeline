"""Redis Pub/Sub for real-time sync progress events"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import redis.asyncio as redis

from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)


class SyncStage(str, Enum):
    """Stages of sync progress"""
    STARTED = "started"
    FETCHING = "fetching_messages"
    PROCESSING = "processing_messages"
    SAVING = "saving_events"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SyncProgressEvent:
    """Sync progress event data"""
    account_id: str
    email_address: str
    stage: SyncStage
    message: str
    timestamp: str
    messages_fetched: int = 0
    events_created: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data["stage"] = self.stage.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncProgressEvent":
        """Create from dictionary"""
        data["stage"] = SyncStage(data["stage"])
        return cls(**data)


class SyncProgressPublisher:
    """Publishes sync progress events to Redis"""

    CHANNEL_PREFIX = "sync_progress"

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis = redis_client
        self.settings = get_settings()
        self._connected = False

    async def connect(self) -> None:
        """Establish Redis connection"""
        if self.redis is None:
            try:
                self.redis = redis.Redis(
                    host=self.settings.redis_host,
                    port=self.settings.redis_port,
                    db=self.settings.redis_db,
                    password=self.settings.redis_password or None,
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                await self.redis.ping()
                self._connected = True
                logger.info("Redis pub/sub publisher connected")
            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(f"Redis pub/sub connection failed: {e}")
                self._connected = False
                self.redis = None

    async def disconnect(self) -> None:
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            self._connected = False
            logger.info("Redis pub/sub publisher disconnected")

    def is_available(self) -> bool:
        """Check if Redis is connected"""
        return self._connected and self.redis is not None

    def _get_channel(self, tenant_id: str) -> str:
        """Get channel name for tenant"""
        return f"{self.CHANNEL_PREFIX}:{tenant_id}"

    async def publish(self, tenant_id: str, event: SyncProgressEvent) -> bool:
        """
        Publish sync progress event to tenant channel

        Args:
            tenant_id: Tenant to publish to
            event: Progress event data

        Returns:
            True if published successfully
        """
        if not self.is_available() or self.redis is None:
            logger.debug("Redis not available, skipping publish")
            return False

        try:
            channel = self._get_channel(tenant_id)
            message = json.dumps(event.to_dict())
            await self.redis.publish(channel, message)
            logger.debug(f"Published sync progress to {channel}: {event.stage.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish sync progress: {e}")
            return False

    async def publish_started(
        self,
        tenant_id: str,
        account_id: str,
        email_address: str,
    ) -> bool:
        """Publish sync started event"""
        event = SyncProgressEvent(
            account_id=account_id,
            email_address=email_address,
            stage=SyncStage.STARTED,
            message="Sync started",
            timestamp=datetime.utcnow().isoformat(),
        )
        return await self.publish(tenant_id, event)

    async def publish_fetching(
        self,
        tenant_id: str,
        account_id: str,
        email_address: str,
    ) -> bool:
        """Publish fetching messages event"""
        event = SyncProgressEvent(
            account_id=account_id,
            email_address=email_address,
            stage=SyncStage.FETCHING,
            message="Fetching messages from provider",
            timestamp=datetime.utcnow().isoformat(),
        )
        return await self.publish(tenant_id, event)

    async def publish_processing(
        self,
        tenant_id: str,
        account_id: str,
        email_address: str,
        messages_fetched: int,
    ) -> bool:
        """Publish processing messages event"""
        event = SyncProgressEvent(
            account_id=account_id,
            email_address=email_address,
            stage=SyncStage.PROCESSING,
            message=f"Processing {messages_fetched} messages",
            timestamp=datetime.utcnow().isoformat(),
            messages_fetched=messages_fetched,
        )
        return await self.publish(tenant_id, event)

    async def publish_saving(
        self,
        tenant_id: str,
        account_id: str,
        email_address: str,
        messages_fetched: int,
        events_created: int,
    ) -> bool:
        """Publish saving events event"""
        event = SyncProgressEvent(
            account_id=account_id,
            email_address=email_address,
            stage=SyncStage.SAVING,
            message=f"Saving {events_created} new events",
            timestamp=datetime.utcnow().isoformat(),
            messages_fetched=messages_fetched,
            events_created=events_created,
        )
        return await self.publish(tenant_id, event)

    async def publish_completed(
        self,
        tenant_id: str,
        account_id: str,
        email_address: str,
        messages_fetched: int,
        events_created: int,
    ) -> bool:
        """Publish sync completed event"""
        event = SyncProgressEvent(
            account_id=account_id,
            email_address=email_address,
            stage=SyncStage.COMPLETED,
            message="Sync completed successfully",
            timestamp=datetime.utcnow().isoformat(),
            messages_fetched=messages_fetched,
            events_created=events_created,
        )
        return await self.publish(tenant_id, event)

    async def publish_failed(
        self,
        tenant_id: str,
        account_id: str,
        email_address: str,
        error: str,
    ) -> bool:
        """Publish sync failed event"""
        event = SyncProgressEvent(
            account_id=account_id,
            email_address=email_address,
            stage=SyncStage.FAILED,
            message="Sync failed",
            timestamp=datetime.utcnow().isoformat(),
            error=error,
        )
        return await self.publish(tenant_id, event)


class SyncProgressSubscriber:
    """Subscribes to sync progress events from Redis"""

    CHANNEL_PREFIX = "sync_progress"

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis = redis_client
        self.settings = get_settings()
        self._connected = False
        self._pubsub: redis.client.PubSub | None = None

    async def connect(self) -> None:
        """Establish Redis connection"""
        if self.redis is None:
            try:
                self.redis = redis.Redis(
                    host=self.settings.redis_host,
                    port=self.settings.redis_port,
                    db=self.settings.redis_db,
                    password=self.settings.redis_password or None,
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                await self.redis.ping()
                self._connected = True
                logger.info("Redis pub/sub subscriber connected")
            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(f"Redis pub/sub connection failed: {e}")
                self._connected = False
                self.redis = None

    async def disconnect(self) -> None:
        """Close Redis connection and pubsub"""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self.redis:
            await self.redis.close()
            self._connected = False
            logger.info("Redis pub/sub subscriber disconnected")

    def is_available(self) -> bool:
        """Check if Redis is connected"""
        return self._connected and self.redis is not None

    def _get_channel(self, tenant_id: str) -> str:
        """Get channel name for tenant"""
        return f"{self.CHANNEL_PREFIX}:{tenant_id}"

    async def subscribe(self, tenant_id: str) -> AsyncIterator[SyncProgressEvent]:
        """
        Subscribe to sync progress events for a tenant

        Args:
            tenant_id: Tenant to subscribe to

        Yields:
            SyncProgressEvent objects as they arrive
        """
        if not self.is_available() or self.redis is None:
            logger.warning("Redis not available for subscription")
            return

        channel = self._get_channel(tenant_id)
        self._pubsub = self.redis.pubsub()

        try:
            await self._pubsub.subscribe(channel)
            logger.info(f"Subscribed to {channel}")

            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        event = SyncProgressEvent.from_dict(data)
                        yield event
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.error(f"Failed to parse sync progress message: {e}")
                        continue

        except Exception as e:
            logger.error(f"Subscription error: {e}")
        finally:
            if self._pubsub:
                await self._pubsub.unsubscribe(channel)
                logger.info(f"Unsubscribed from {channel}")


# Global publisher instance (initialized on app startup)
_publisher: SyncProgressPublisher | None = None


def get_sync_publisher() -> SyncProgressPublisher | None:
    """Get the global sync progress publisher"""
    return _publisher


def set_sync_publisher(publisher: SyncProgressPublisher) -> None:
    """Set the global sync progress publisher"""
    global _publisher
    _publisher = publisher
