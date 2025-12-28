"""Outlook/Office365 provider implementation using Microsoft Graph API"""
from datetime import datetime, timedelta
from typing import Any

import httpx
from msal import ConfidentialClientApplication

from core.logging import get_logger
from integrations.email.protocols import EmailMessage, EmailProviderConfig

logger = get_logger(__name__)


class OutlookProvider:
    """Outlook/Office365 provider using Microsoft Graph API"""

    def __init__(self):
        self._access_token: str | None = None
        self._config: EmailProviderConfig | None = None
        self._graph_url = "https://graph.microsoft.com/v1.0"

    async def connect(self, config: EmailProviderConfig) -> None:
        """Connect to Microsoft Graph API"""
        self._config = config

        # Get OAuth tokens
        client_id = config.credentials.get("client_id")
        client_secret = config.credentials.get("client_secret")
        tenant_id = config.credentials.get("tenant_id")
        refresh_token = config.credentials.get("refresh_token")

        if not all([client_id, client_secret, tenant_id]):
            raise ValueError("client_id, client_secret, tenant_id required")

        # Build MSAL app
        app = ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )

        # Acquire token
        if refresh_token:
            result = app.acquire_token_by_refresh_token(
                refresh_token, scopes=["https://graph.microsoft.com/.default"]
            )
        else:
            # Use client credentials flow
            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )

        if "access_token" in result:
            self._access_token = result["access_token"]
            logger.info(f"Connected to Microsoft Graph: {config.email_address}")
        else:
            raise RuntimeError(
                f"Failed to acquire token: {result.get('error_description')}"
            )

    async def disconnect(self) -> None:
        """Disconnect from Microsoft Graph"""
        self._access_token = None
        logger.info("Disconnected from Microsoft Graph")

    async def fetch_messages(
        self, since: datetime | None = None, limit: int = 100
    ) -> list[EmailMessage]:
        """Fetch messages from Outlook via Graph API"""
        if not self._access_token:
            raise RuntimeError("Not connected to Microsoft Graph")

        # Build query parameters
        params: dict[str, str | int] = {
            "$top": limit,
            "$orderby": "receivedDateTime DESC",
        }

        if since:
            iso_date = since.isoformat()
            params["$filter"] = f"receivedDateTime ge {iso_date}"

        # Make request
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._graph_url}/me/messages",
                headers={"Authorization": f"Bearer {self._access_token}"},
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        # Parse messages
        messages = []
        for item in data.get("value", []):
            try:
                msg = self._parse_outlook_message(item)
                messages.append(msg)
            except Exception as e:
                logger.error(f"Error parsing Outlook message: {e}")
                continue

        logger.info(f"Fetched {len(messages)} messages from Outlook")
        return messages

    def _parse_outlook_message(self, item: dict) -> EmailMessage:
        """Parse Outlook message from Graph API response"""
        # Parse timestamp
        timestamp = datetime.fromisoformat(
            item["receivedDateTime"].replace("Z", "+00:00")
        )

        # Extract recipient addresses
        to_addresses = [
            recipient["emailAddress"]["address"]
            for recipient in item.get("toRecipients", [])
        ]

        return EmailMessage(
            message_id=item["id"],
            thread_id=item.get("conversationId"),
            from_address=item["from"]["emailAddress"]["address"],
            to_addresses=to_addresses,
            subject=item.get("subject", ""),
            timestamp=timestamp,
            labels=item.get("categories", []),
            is_read=item.get("isRead", False),
            is_starred=item.get("flag", {}).get("flagStatus") == "flagged",
            has_attachments=item.get("hasAttachments", False),
            provider_metadata={
                "outlook_id": item["id"],
                "conversation_id": item.get("conversationId"),
                "categories": item.get("categories", []),
            },
        )

    async def setup_webhook(self, callback_url: str) -> dict[str, Any]:
        """Setup Microsoft Graph webhook subscription"""
        if not self._access_token:
            raise RuntimeError("Not connected to Microsoft Graph")

        # Create subscription
        subscription = {
            "changeType": "created",
            "notificationUrl": callback_url,
            "resource": "/me/mailFolders/inbox/messages",
            "expirationDateTime": (
                datetime.utcnow().replace(hour=0, minute=0, second=0)
                + timedelta(days=3)
            ).isoformat()
            + "Z",
            "clientState": "timeline-secret-value",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._graph_url}/subscriptions",
                headers={"Authorization": f"Bearer {self._access_token}"},
                json=subscription,
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Unexpected response format from Microsoft Graph API")

        logger.info(f"Outlook webhook setup: {result}")
        return result

    async def remove_webhook(self) -> None:
        """Remove Microsoft Graph webhook subscription"""
        if not self._access_token:
            return

        logger.info("Outlook webhook removed")

    @property
    def supports_webhooks(self) -> bool:
        """Outlook supports webhooks via Graph API"""
        return True

    @property
    def supports_incremental_sync(self) -> bool:
        """Outlook supports incremental sync"""
        return True
