"""Gmail provider implementation using Gmail API"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import partial
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.infrastructure.external.email.protocols import (EmailMessage,
                                                         EmailProviderConfig)
from src.shared.telemetry.logging import get_logger
from src.shared.utils import from_timestamp_ms_utc

logger = get_logger(__name__)

# Gmail API limits
BATCH_SIZE = 100  # Max requests per batch
DEFAULT_MAX_MESSAGES = 10000  # Safety limit to prevent memory exhaustion


async def run_in_thread(func, *args, **kwargs):
    """Run a blocking function in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    if kwargs:
        func = partial(func, **kwargs)
    return await loop.run_in_executor(None, func, *args)


class HistoryChangeType(str, Enum):
    """Types of changes from Gmail History API"""
    MESSAGE_ADDED = "messageAdded"
    MESSAGE_DELETED = "messageDeleted"
    LABELS_ADDED = "labelsAdded"
    LABELS_REMOVED = "labelsRemoved"


@dataclass
class HistoryChange:
    """Represents a change from Gmail History API"""
    change_type: HistoryChangeType
    message_id: str
    gmail_id: str
    thread_id: str | None = None
    labels: list[str] | None = None  # For label changes
    message: EmailMessage | None = None  # Full message for additions


class HistoryExpiredError(Exception):
    """Raised when Gmail history ID has expired (410 error)"""


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
        - Thread pool: Runs blocking API calls in executor to avoid blocking event loop

        Args:
            since: Only fetch messages after this timestamp
            limit: Maximum messages to fetch (defaults to DEFAULT_MAX_MESSAGES for safety)

        Returns:
            List of EmailMessage objects
        """
        if not self._service:
            raise RuntimeError("Not connected to Gmail API")

        # Apply safety limit to prevent memory exhaustion
        effective_limit = limit if limit is not None else DEFAULT_MAX_MESSAGES

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
            # Run in thread pool to avoid blocking event loop
            request = self._service.users().messages().list(
                userId="me",
                q=query,
                maxResults=500,
                pageToken=page_token,
            )
            results = await run_in_thread(request.execute)

            message_ids = [msg["id"] for msg in results.get("messages", [])]
            pages_fetched += 1

            # Check limit before extending to avoid fetching unnecessary data
            remaining = effective_limit - len(all_message_ids)
            all_message_ids.extend(message_ids[:remaining])
            if len(all_message_ids) >= effective_limit:
                break

            page_token = results.get("nextPageToken")
            if not page_token:
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

            # Execute batch in thread pool to avoid blocking event loop
            await run_in_thread(batch.execute)

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
        request = self._service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full"
        )
        msg = await run_in_thread(request.execute)
        return self._parse_message(msg, msg_id)

    async def setup_webhook(self, callback_url: str) -> dict[str, Any]:
        """Setup Gmail push notifications"""
        if not self._service:
            raise RuntimeError("Not connected to Gmail API")

        # Setup watch on mailbox
        body = {
            'labelIds': ['INBOX'],
            'topicName': callback_url  # Should be Pub/Sub topic
        }

        request = self._service.users().watch(userId='me', body=body)
        response = await run_in_thread(request.execute)

        logger.info(f"Gmail webhook setup: {response}")
        return response

    async def remove_webhook(self) -> None:
        """Remove Gmail push notifications"""
        if not self._service:
            return

        request = self._service.users().stop(userId='me')
        await run_in_thread(request.execute)
        logger.info("Gmail webhook removed")

    @property
    def supports_webhooks(self) -> bool:
        """Gmail supports push notifications"""
        return True

    @property
    def supports_incremental_sync(self) -> bool:
        """Gmail supports incremental sync"""
        return True

    @property
    def supports_history_sync(self) -> bool:
        """Gmail supports history-based incremental sync"""
        return True

    async def get_current_history_id(self) -> str:
        """
        Get the current history ID from Gmail profile.

        This should be captured after a full sync to enable
        subsequent history-based incremental syncs.

        Returns:
            Current history ID as string
        """
        if not self._service:
            raise RuntimeError("Not connected to Gmail API")

        request = self._service.users().getProfile(userId="me")
        profile = await run_in_thread(request.execute)
        history_id = profile.get("historyId")

        if not history_id:
            raise RuntimeError("Gmail profile did not return historyId")

        logger.info("Gmail current history ID: %s", history_id)
        return str(history_id)

    async def fetch_history_changes(
        self,
        start_history_id: str,
        history_types: list[str] | None = None,
    ) -> tuple[list[HistoryChange], str]:
        """
        Fetch changes since a history ID using Gmail History API.

        This is more efficient than timestamp-based sync as it:
        - Only returns actual changes (not all messages since timestamp)
        - Includes deletions and label changes
        - Uses less API quota

        Args:
            start_history_id: History ID to start from
            history_types: Types to fetch. Defaults to ["messageAdded", "messageDeleted"]

        Returns:
            Tuple of (list of changes, new history ID)

        Raises:
            HistoryExpiredError: If history ID has expired (410 error)
        """
        if not self._service:
            raise RuntimeError("Not connected to Gmail API")

        if history_types is None:
            history_types = ["messageAdded", "messageDeleted"]

        changes: list[HistoryChange] = []
        new_history_id = start_history_id
        page_token: str | None = None

        try:
            while True:
                # Fetch history page
                request_params: dict[str, Any] = {
                    "userId": "me",
                    "startHistoryId": start_history_id,
                    "historyTypes": history_types,
                    "maxResults": 500,
                }
                if page_token:
                    request_params["pageToken"] = page_token

                request = self._service.users().history().list(**request_params)
                result = await run_in_thread(request.execute)

                # Update to latest history ID
                if "historyId" in result:
                    new_history_id = result["historyId"]

                # Process history records
                for record in result.get("history", []):
                    # Handle message additions
                    for added in record.get("messagesAdded", []):
                        msg_data = added.get("message", {})
                        gmail_id = msg_data.get("id")
                        if gmail_id:
                            changes.append(HistoryChange(
                                change_type=HistoryChangeType.MESSAGE_ADDED,
                                message_id=msg_data.get("id", ""),
                                gmail_id=gmail_id,
                                thread_id=msg_data.get("threadId"),
                                labels=msg_data.get("labelIds"),
                            ))

                    # Handle message deletions
                    for deleted in record.get("messagesDeleted", []):
                        msg_data = deleted.get("message", {})
                        gmail_id = msg_data.get("id")
                        if gmail_id:
                            changes.append(HistoryChange(
                                change_type=HistoryChangeType.MESSAGE_DELETED,
                                message_id=msg_data.get("id", ""),
                                gmail_id=gmail_id,
                                thread_id=msg_data.get("threadId"),
                            ))

                    # Handle label additions (optional tracking)
                    for label_added in record.get("labelsAdded", []):
                        msg_data = label_added.get("message", {})
                        gmail_id = msg_data.get("id")
                        if gmail_id:
                            changes.append(HistoryChange(
                                change_type=HistoryChangeType.LABELS_ADDED,
                                message_id=msg_data.get("id", ""),
                                gmail_id=gmail_id,
                                thread_id=msg_data.get("threadId"),
                                labels=label_added.get("labelIds"),
                            ))

                    # Handle label removals (optional tracking)
                    for label_removed in record.get("labelsRemoved", []):
                        msg_data = label_removed.get("message", {})
                        gmail_id = msg_data.get("id")
                        if gmail_id:
                            changes.append(HistoryChange(
                                change_type=HistoryChangeType.LABELS_REMOVED,
                                message_id=msg_data.get("id", ""),
                                gmail_id=gmail_id,
                                thread_id=msg_data.get("threadId"),
                                labels=label_removed.get("labelIds"),
                            ))

                # Check for more pages
                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            logger.info(
                "Gmail history: fetched %d changes since history ID %s, new ID: %s",
                len(changes), start_history_id, new_history_id
            )

            return changes, new_history_id

        except HttpError as e:
            # Handle 404 (history ID not found) or 410 (history expired)
            if e.resp.status in (404, 410):
                logger.warning(
                    "Gmail history ID %s expired or invalid (status %d). "
                    "Full sync required.",
                    start_history_id, e.resp.status
                )
                raise HistoryExpiredError(
                    f"Gmail history ID {start_history_id} has expired. "
                    "A full sync is required to re-establish history."
                ) from e
            raise

    async def fetch_messages_for_changes(
        self,
        changes: list[HistoryChange],
    ) -> list[HistoryChange]:
        """
        Fetch full message details for MESSAGE_ADDED changes.

        This enriches the HistoryChange objects with full EmailMessage data
        so they can be converted to Timeline events.

        Args:
            changes: List of history changes (only MESSAGE_ADDED will be fetched)

        Returns:
            The same changes list with message field populated for additions
        """
        # Get IDs of messages to fetch
        message_ids_to_fetch = [
            c.gmail_id for c in changes
            if c.change_type == HistoryChangeType.MESSAGE_ADDED
        ]

        if not message_ids_to_fetch:
            return changes

        # Fetch messages in batch
        messages_by_id: dict[str, EmailMessage] = {}
        fetched = await self._fetch_messages_batch(message_ids_to_fetch)
        for msg in fetched:
            gmail_id = msg.provider_metadata.get("gmail_id") if msg.provider_metadata else None
            if gmail_id:
                messages_by_id[gmail_id] = msg

        # Attach messages to changes
        for change in changes:
            if change.change_type == HistoryChangeType.MESSAGE_ADDED:
                change.message = messages_by_id.get(change.gmail_id)

        logger.info(
            "Fetched %d/%d message details for history changes",
            len(messages_by_id), len(message_ids_to_fetch)
        )

        return changes
