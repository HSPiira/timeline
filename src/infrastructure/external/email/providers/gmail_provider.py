"""Gmail provider implementation using Gmail API"""
from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import BatchHttpRequest

from src.infrastructure.external.email.protocols import (EmailMessage,
                                                         EmailProviderConfig)
from src.shared.telemetry.logging import get_logger
from src.shared.utils import from_timestamp_ms_utc

logger = get_logger(__name__)

# Gmail batch API limits
BATCH_SIZE = 100  # Max requests per batch


class GmailProvider:
    """Gmail provider using Gmail API with batch optimization"""

    def __init__(self) -> None:
        self._service: Any = None
        self._config: EmailProviderConfig | None = None

    async def connect(self, config: EmailProviderConfig) -> None:
        """Connect to Gmail API"""
        self._config = config

        # Build credentials from OAuth tokens
        creds = Credentials(
            token=config.credentials.get('access_token'),
            refresh_token=config.credentials.get('refresh_token'),
            token_uri='https://oauth2.googleapis.com/token',
            client_id=config.credentials.get('client_id'),
            client_secret=config.credentials.get('client_secret')
        )

        # Build Gmail service
        self._service = build('gmail', 'v1', credentials=creds)
        logger.info(f"Connected to Gmail API: {config.email_address}")

    async def disconnect(self) -> None:
        """Disconnect from Gmail API"""
        self._service = None
        logger.info("Disconnected from Gmail API")

    async def fetch_messages(
        self,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[EmailMessage]:
        """
        Fetch messages from Gmail using batch API with pagination.

        Performance optimizations:
        - Batch API: Fetches up to 100 messages per request (vs N+1 before)
        - Pagination: Automatically fetches all matching messages

        Args:
            since: Only fetch messages after this timestamp
            limit: Optional maximum messages to fetch (None = no limit)

        Returns:
            List of EmailMessage objects
        """
        if not self._service:
            raise RuntimeError("Not connected to Gmail API")

        # Build query
        query = ""
        if since:
            timestamp = int(since.timestamp())
            query = f"after:{timestamp}"

        # Collect all message IDs with pagination
        all_message_ids: list[str] = []
        page_token: str | None = None
        pages_fetched = 0

        while True:
            # Request up to 500 per page (Gmail's max per request)
            results = self._service.users().messages().list(
                userId="me",
                q=query,
                maxResults=500,
                pageToken=page_token,
            ).execute()

            message_ids = [msg["id"] for msg in results.get("messages", [])]
            all_message_ids.extend(message_ids)
            pages_fetched += 1

            page_token = results.get("nextPageToken")
            if not page_token:
                break

            # Check optional limit
            if limit and len(all_message_ids) >= limit:
                all_message_ids = all_message_ids[:limit]
                break

            logger.debug(
                "Gmail pagination: fetched %d IDs (page %d), continuing...",
                len(all_message_ids), pages_fetched
            )

        logger.info(
            "Gmail: collected %d message IDs in %d pages",
            len(all_message_ids), pages_fetched
        )

        # Fetch full messages using batch API
        messages = await self._fetch_messages_batch(all_message_ids)

        logger.info("Fetched %d messages from Gmail", len(messages))
        return messages

    async def _fetch_messages_batch(self, message_ids: list[str]) -> list[EmailMessage]:
        """
        Fetch multiple messages using Gmail batch API.

        Reduces N API calls to ceil(N/100) batch requests.
        """
        if not message_ids:
            return []

        messages: list[EmailMessage] = []
        errors: list[str] = []

        # Process in batches of BATCH_SIZE
        for batch_start in range(0, len(message_ids), BATCH_SIZE):
            batch_ids = message_ids[batch_start:batch_start + BATCH_SIZE]
            batch_results: dict[str, dict[str, Any]] = {}

            def create_callback(msg_id: str):
                def callback(request_id: str, response: dict[str, Any], exception: Exception | None):
                    if exception:
                        errors.append(f"{msg_id}: {exception}")
                    else:
                        batch_results[msg_id] = response
                return callback

            # Build batch request
            batch = self._service.new_batch_http_request()
            for msg_id in batch_ids:
                batch.add(
                    self._service.users().messages().get(
                        userId="me",
                        id=msg_id,
                        format="full"
                    ),
                    callback=create_callback(msg_id)
                )

            # Execute batch
            batch.execute()

            # Parse results
            for msg_id in batch_ids:
                if msg_id in batch_results:
                    try:
                        parsed = self._parse_message(batch_results[msg_id], msg_id)
                        if parsed:
                            messages.append(parsed)
                    except Exception as e:
                        errors.append(f"{msg_id}: {e}")

            logger.debug(
                "Gmail batch: processed %d/%d messages",
                batch_start + len(batch_ids), len(message_ids)
            )

        if errors:
            logger.warning("Gmail batch had %d errors: %s", len(errors), errors[:5])

        return messages

    def _parse_message(self, msg: dict[str, Any], msg_id: str) -> EmailMessage | None:
        """Parse Gmail API message response into EmailMessage."""
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

        timestamp = from_timestamp_ms_utc(int(msg["internalDate"]))
        label_ids = msg.get("labelIds", [])

        return EmailMessage(
            message_id=headers.get("Message-ID", msg_id),
            thread_id=msg.get("threadId"),
            from_address=headers.get("From", ""),
            to_addresses=[addr.strip() for addr in headers.get("To", "").split(",")],
            subject=headers.get("Subject", ""),
            timestamp=timestamp,
            labels=label_ids,
            is_read="UNREAD" not in label_ids,
            is_starred="STARRED" in label_ids,
            has_attachments=any(
                part.get("filename")
                for part in msg["payload"].get("parts", [])
            ),
            provider_metadata={
                "gmail_id": msg_id,
                "thread_id": msg.get("threadId"),
                "label_ids": label_ids,
            },
        )

    async def _fetch_and_parse_message(self, msg_id: str) -> EmailMessage | None:
        """Fetch and parse a single Gmail message (legacy, prefer batch)."""
        msg = self._service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full"
        ).execute()
        return self._parse_message(msg, msg_id)

    async def setup_webhook(self, callback_url: str) -> dict[str, Any]:
        """Setup Gmail push notifications"""
        if not self._service:
            raise RuntimeError("Not connected to Gmail API")

        # Setup watch on mailbox
        request = {
            'labelIds': ['INBOX'],
            'topicName': callback_url  # Should be Pub/Sub topic
        }

        response = self._service.users().watch(
            userId='me',
            body=request
        ).execute()

        logger.info(f"Gmail webhook setup: {response}")
        return response

    async def remove_webhook(self) -> None:
        """Remove Gmail push notifications"""
        if not self._service:
            return

        self._service.users().stop(userId='me').execute()
        logger.info("Gmail webhook removed")

    @property
    def supports_webhooks(self) -> bool:
        """Gmail supports push notifications"""
        return True

    @property
    def supports_incremental_sync(self) -> bool:
        """Gmail supports incremental sync"""
        return True
