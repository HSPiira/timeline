"""IMAP email provider implementation (works with iCloud, Yahoo, custom servers)"""
import email
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from email.utils import parsedate_to_datetime
import aioimaplib

from integrations.email.protocols import IEmailProvider, EmailMessage, EmailProviderConfig
from core.logging import get_logger

logger = get_logger(__name__)


class IMAPProvider:
    """IMAP provider for universal email access"""

    def __init__(self):
        self._client: Optional[aioimaplib.IMAP4_SSL] = None
        self._config: Optional[EmailProviderConfig] = None

    async def connect(self, config: EmailProviderConfig) -> None:
        """Connect to IMAP server"""
        self._config = config

        # Get IMAP server and port from connection params
        imap_server = config.connection_params.get('imap_server')
        imap_port = config.connection_params.get('imap_port', 993)

        if not imap_server:
            raise ValueError("imap_server required in connection_params")

        # Get credentials
        username = config.credentials.get('username', config.email_address)
        password = config.credentials.get('password')

        if not password:
            raise ValueError("password required in credentials")

        logger.info(f"Connecting to IMAP server: {imap_server}:{imap_port}")

        # Connect using aioimaplib
        self._client = aioimaplib.IMAP4_SSL(host=imap_server, port=imap_port)
        await self._client.wait_hello_from_server()

        # Login
        await self._client.login(username, password)
        logger.info(f"Successfully connected to IMAP: {username}")

    async def disconnect(self) -> None:
        """Disconnect from IMAP server"""
        if self._client:
            await self._client.logout()
            self._client = None
            logger.info("Disconnected from IMAP server")

    async def fetch_messages(
        self,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[EmailMessage]:
        """Fetch messages from IMAP server"""
        if not self._client:
            raise RuntimeError("Not connected to IMAP server")

        # Select INBOX
        await self._client.select('INBOX')

        # Build search criteria
        if since:
            date_str = since.strftime("%d-%b-%Y")
            search_criteria = f'SINCE {date_str}'
        else:
            search_criteria = 'ALL'

        # Search for messages
        _, msg_ids = await self._client.search(search_criteria)
        msg_id_list = msg_ids[0].split()

        # Limit results
        msg_id_list = msg_id_list[-limit:] if len(msg_id_list) > limit else msg_id_list

        messages = []
        for msg_id in msg_id_list:
            try:
                msg = await self._fetch_and_parse_message(msg_id)
                if msg:
                    messages.append(msg)
            except Exception as e:
                logger.error(f"Error fetching message {msg_id}: {e}")
                continue

        logger.info(f"Fetched {len(messages)} messages from IMAP")
        return messages

    async def _fetch_and_parse_message(self, msg_id: bytes) -> Optional[EmailMessage]:
        """Fetch and parse a single message"""
        # Fetch message
        _, msg_data = await self._client.fetch(msg_id, '(RFC822 FLAGS)')

        if not msg_data or not msg_data[1]:
            return None

        # Parse email
        email_body = msg_data[1]
        email_message = email.message_from_bytes(email_body)

        # Extract fields
        message_id = email_message.get('Message-ID', f'imap-{msg_id.decode()}')
        from_address = email_message.get('From', '')
        to_addresses = [addr.strip() for addr in email_message.get('To', '').split(',')]
        subject = email_message.get('Subject', '')

        # Parse date (parsedate_to_datetime returns timezone-aware datetime)
        date_str = email_message.get('Date')
        timestamp = parsedate_to_datetime(date_str) if date_str else datetime.now(timezone.utc)

        # Extract flags
        flags_str = msg_data[0].decode() if msg_data[0] else ''
        is_read = '\\Seen' in flags_str
        is_starred = '\\Flagged' in flags_str

        # Check attachments
        has_attachments = any(part.get_content_disposition() == 'attachment'
                            for part in email_message.walk())

        return EmailMessage(
            message_id=message_id,
            thread_id=email_message.get('In-Reply-To'),
            from_address=from_address,
            to_addresses=to_addresses,
            subject=subject,
            timestamp=timestamp,
            labels=['INBOX'],
            is_read=is_read,
            is_starred=is_starred,
            has_attachments=has_attachments,
            provider_metadata={
                'imap_uid': msg_id.decode(),
                'flags': flags_str
            }
        )

    async def setup_webhook(self, callback_url: str) -> Dict[str, Any]:
        """IMAP doesn't support webhooks"""
        raise NotImplementedError("IMAP does not support webhooks")

    async def remove_webhook(self) -> None:
        """IMAP doesn't support webhooks"""
        pass

    @property
    def supports_webhooks(self) -> bool:
        """IMAP doesn't support webhooks"""
        return False

    @property
    def supports_incremental_sync(self) -> bool:
        """IMAP supports incremental sync via SINCE"""
        return True
