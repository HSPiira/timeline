"""WebSocket endpoints for real-time sync progress"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.infrastructure.messaging.redis_pubsub import (
    SyncProgressSubscriber,
    get_sync_publisher,
)
from src.infrastructure.security.jwt import verify_token
from src.presentation.api.websocket.manager import get_connection_manager

logger = logging.getLogger(__name__)

router = APIRouter()


async def validate_websocket_token(token: str) -> dict[str, Any] | None:
    """
    Validate JWT token for WebSocket authentication.

    Args:
        token: JWT token from query parameter

    Returns:
        Token payload if valid, None otherwise
    """
    try:
        payload = verify_token(token)
        return payload
    except ValueError as e:
        logger.warning(f"WebSocket auth failed: {e}")
        return None
    except Exception as e:
        logger.error(f"WebSocket auth error: {e}")
        return None


@router.websocket("/ws/sync-progress")
async def sync_progress_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token"),
):
    """
    WebSocket endpoint for real-time sync progress updates.

    Query Parameters:
        token: JWT bearer token for authentication

    Message Format (outgoing):
        {
            "account_id": "...",
            "email_address": "...",
            "stage": "started|fetching_messages|processing_messages|saving_events|completed|failed",
            "message": "...",
            "timestamp": "ISO8601",
            "messages_fetched": 0,
            "events_created": 0,
            "error": null
        }
    """
    # Validate token before accepting connection
    payload = await validate_websocket_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid authentication token")
        return

    tenant_id = payload.get("tenant_id")
    user_id = payload.get("sub")

    if not tenant_id:
        await websocket.close(code=4002, reason="Missing tenant_id in token")
        return

    manager = get_connection_manager()
    subscriber = SyncProgressSubscriber()

    try:
        # Accept connection and register with manager
        await manager.connect(websocket, tenant_id)

        # Send connection confirmation
        await manager.send_personal(websocket, {
            "type": "connected",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "message": "Connected to sync progress stream",
        })

        # Connect to Redis for pub/sub
        await subscriber.connect()

        if not subscriber.is_available():
            # Redis not available - notify client and keep connection for direct broadcasts
            await manager.send_personal(websocket, {
                "type": "warning",
                "message": "Real-time updates may be delayed - pub/sub not available",
            })

            # Keep connection alive with ping/pong
            while True:
                try:
                    # Wait for messages from client (ping/pong or disconnect)
                    data = await websocket.receive_text()
                    if data == "ping":
                        await websocket.send_text("pong")
                except WebSocketDisconnect:
                    break
        else:
            # Create tasks for reading from client and Redis
            async def read_client():
                """Handle incoming messages from client"""
                try:
                    while True:
                        data = await websocket.receive_text()
                        if data == "ping":
                            await websocket.send_text("pong")
                except WebSocketDisconnect:
                    pass

            async def read_redis():
                """Forward Redis pub/sub messages to WebSocket"""
                try:
                    async for event in subscriber.subscribe(tenant_id):
                        message = {
                            "type": "sync_progress",
                            **event.to_dict(),
                        }
                        await manager.send_personal(websocket, message)
                except asyncio.CancelledError:
                    pass

            # Run both tasks concurrently
            client_task = asyncio.create_task(read_client())
            redis_task = asyncio.create_task(read_redis())

            try:
                # Wait for either task to complete (client disconnect or error)
                done, pending = await asyncio.wait(
                    [client_task, redis_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            except Exception as e:
                logger.error(f"WebSocket task error: {e}")
                client_task.cancel()
                redis_task.cancel()

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"WebSocket error for tenant {tenant_id}: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
    finally:
        await manager.disconnect(websocket, tenant_id)
        await subscriber.disconnect()


@router.get("/ws/status")
async def websocket_status():
    """
    Get WebSocket connection status.

    Returns connection counts for monitoring.
    """
    manager = get_connection_manager()
    publisher = get_sync_publisher()

    return {
        "total_connections": manager.get_total_connections(),
        "publisher_available": publisher.is_available() if publisher else False,
    }
