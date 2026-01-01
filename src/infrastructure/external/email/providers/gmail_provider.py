"""Gmail provider implementation using Gmail API"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.infrastructure.external.email.protocols import (EmailMessage,
                                                         EmailProviderConfig)
from src.shared.telemetry.logging import get_logger

logger = get_logger(__name__)


class GmailProvider:
    """Gmail provider using Gmail API"""

    def __init__(self):
        self._service = None
        self._config: Optional[EmailProviderConfig] = None

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
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[EmailMessage]:
        """Fetch messages from Gmail"""
        if not self._service:
            raise RuntimeError("Not connected to Gmail API")

        # Build query
        query = ''
        if since:
            timestamp = int(since.timestamp())
            query = f'after:{timestamp}'

        # List messages
        results = self._service.users().messages().list(
            userId='me',
            q=query,
            maxResults=limit
        ).execute()

        message_ids = [msg['id'] for msg in results.get('messages', [])]

        # Fetch full message details
        messages = []
        for msg_id in message_ids:
            try:
                msg = await self._fetch_and_parse_message(msg_id)
                if msg:
                    messages.append(msg)
            except Exception as e:
                logger.error(f"Error fetching Gmail message {msg_id}: {e}")
                continue

        logger.info(f"Fetched {len(messages)} messages from Gmail")
        return messages

    async def _fetch_and_parse_message(self, msg_id: str) -> Optional[EmailMessage]:
        """Fetch and parse a single Gmail message"""
        msg = self._service.users().messages().get(
            userId='me',
            id=msg_id,
            format='full'
        ).execute()

        # Extract headers
        headers = {h['name']: h['value'] for h in msg['payload']['headers']}

        # Parse timestamp
        timestamp = datetime.fromtimestamp(int(msg['internalDate']) / 1000)

        # Extract labels
        label_ids = msg.get('labelIds', [])

        return EmailMessage(
            message_id=headers.get('Message-ID', msg_id),
            thread_id=msg.get('threadId'),
            from_address=headers.get('From', ''),
            to_addresses=[addr.strip() for addr in headers.get('To', '').split(',')],
            subject=headers.get('Subject', ''),
            timestamp=timestamp,
            labels=label_ids,
            is_read='UNREAD' not in label_ids,
            is_starred='STARRED' in label_ids,
            has_attachments=any(
                part.get('filename')
                for part in msg['payload'].get('parts', [])
            ),
            provider_metadata={
                'gmail_id': msg_id,
                'thread_id': msg.get('threadId'),
                'label_ids': label_ids
            }
        )

    async def setup_webhook(self, callback_url: str) -> Dict[str, Any]:
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
