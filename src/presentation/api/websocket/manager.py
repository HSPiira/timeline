"""WebSocket connection manager for real-time sync progress"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections per tenant.

    Handles:
    - Connection registration/deregistration
    - Tenant-scoped broadcasting
    - Connection health monitoring
    """

    def __init__(self) -> None:
        # Map of tenant_id -> list of active WebSocket connections
        self.active_connections: dict[str, list[WebSocket]] = defaultdict(list)
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, tenant_id: str) -> None:
        """
        Accept and register a WebSocket connection.

        Args:
            websocket: The WebSocket connection to accept
            tenant_id: Tenant ID to associate with connection
        """
        await websocket.accept()

        async with self._lock:
            self.active_connections[tenant_id].append(websocket)

        logger.info(
            f"WebSocket connected for tenant {tenant_id}. "
            f"Total connections for tenant: {len(self.active_connections[tenant_id])}"
        )

    async def disconnect(self, websocket: WebSocket, tenant_id: str) -> None:
        """
        Remove a WebSocket connection.

        Args:
            websocket: The WebSocket connection to remove
            tenant_id: Tenant ID associated with connection
        """
        async with self._lock:
            if tenant_id in self.active_connections:
                try:
                    self.active_connections[tenant_id].remove(websocket)
                    if not self.active_connections[tenant_id]:
                        del self.active_connections[tenant_id]
                except ValueError:
                    pass  # Connection already removed

        logger.info(f"WebSocket disconnected for tenant {tenant_id}")

    async def broadcast_to_tenant(self, tenant_id: str, message: dict[str, Any]) -> int:
        """
        Send message to all connections for a tenant.

        Args:
            tenant_id: Tenant to broadcast to
            message: Message data to send

        Returns:
            Number of connections that received the message
        """
        if tenant_id not in self.active_connections:
            return 0

        connections = self.active_connections[tenant_id].copy()
        if not connections:
            return 0

        message_text = json.dumps(message)
        sent_count = 0
        failed_connections: list[WebSocket] = []

        for connection in connections:
            try:
                await connection.send_text(message_text)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                failed_connections.append(connection)

        # Clean up failed connections
        if failed_connections:
            async with self._lock:
                for conn in failed_connections:
                    try:
                        self.active_connections[tenant_id].remove(conn)
                    except ValueError:
                        pass

        logger.debug(
            f"Broadcast to tenant {tenant_id}: {sent_count}/{len(connections)} successful"
        )
        return sent_count

    async def send_personal(self, websocket: WebSocket, message: dict[str, Any]) -> bool:
        """
        Send message to a specific connection.

        Args:
            websocket: Target WebSocket connection
            message: Message data to send

        Returns:
            True if sent successfully
        """
        try:
            await websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")
            return False

    def get_connection_count(self, tenant_id: str) -> int:
        """Get number of active connections for a tenant"""
        return len(self.active_connections.get(tenant_id, []))

    def get_total_connections(self) -> int:
        """Get total number of active connections across all tenants"""
        return sum(len(conns) for conns in self.active_connections.values())

    async def close_all(self) -> None:
        """Close all WebSocket connections (for shutdown)"""
        async with self._lock:
            for tenant_id, connections in self.active_connections.items():
                for conn in connections:
                    try:
                        await conn.close()
                    except Exception as e:
                        logger.debug(f"Error closing WebSocket: {e}")
            self.active_connections.clear()
        logger.info("All WebSocket connections closed")


# Global connection manager instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager, creating if needed"""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


def set_connection_manager(manager: ConnectionManager) -> None:
    """Set the global connection manager (for testing)"""
    global _manager
    _manager = manager
