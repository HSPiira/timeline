"""Gmail provider implementation using Gmail API"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from integrations.email.protocols import IEmailProvider, EmailMessage, EmailProviderConfig
from core.logging import get_logger

logger = get_logger(__name__)


class GmailProvider:
    """
    Gmail provider using Gmail API with automatic token refresh.

    Implements: IEmailProvider

    Note: Gmail webhooks require Google Cloud Pub/Sub configuration.
    """

    def __init__(self) -> None:
        self._service = None
        self._config: Optional[EmailProviderConfig] = None
        self._credentials: Optional[Credentials] = None
        self._token_refresh_callback: Optional[Callable] = None

    def set_token_refresh_callback(self, callback: Callable[[Dict], None]):
        """
        Set callback to be called when tokens are refreshed.

        The callback receives the updated credentials dict.
        This allows the sync service to save refreshed tokens back to the database.
        """
        self._token_refresh_callback = callback

    async def connect(self, config: EmailProviderConfig) -> None:
        """Connect to Gmail API with automatic token refresh"""
        self._config = config

        # Validate required credentials
        required_keys = ['access_token', 'refresh_token', 'client_id', 'client_secret']
        missing = [k for k in required_keys if not config.credentials.get(k)]
        if missing:
            raise ValueError(f"Missing required Gmail OAuth credentials: {missing}")

        # Build credentials from OAuth tokens
        # Include scopes and enable automatic token refresh
        self._credentials = Credentials(
            token=config.credentials.get('access_token'),
            refresh_token=config.credentials.get('refresh_token'),
            token_uri='https://oauth2.googleapis.com/token',
            client_id=config.credentials['client_id'],
            client_secret=config.credentials['client_secret'],
            scopes=['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']
        )

        try:
            # Build Gmail service
            # The service will automatically refresh tokens when they expire
            self._service = build('gmail', 'v2', credentials=self._credentials)

            # Proactively check and refresh tokens if needed
            if self._credentials.expired:
                logger.info(f"Access token expired for {config.email_address}, refreshing...")
                from google.auth.transport.requests import Request
                self._credentials.refresh(Request())
                await self._check_and_refresh_tokens()

            logger.info(f"Connected to Gmail API: {config.email_address}")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Gmail API: {e}") from e

    async def _check_and_refresh_tokens(self):
        """
        Check if credentials were refreshed and notify callback.

        Google's OAuth library automatically refreshes tokens when needed.
        We just need to check if they changed and notify our callback.
        """
        if not self._credentials or not self._token_refresh_callback:
            return

        # Check if token was refreshed
        current_token = self._credentials.token
        original_token = self._config.credentials.get('access_token')

        if current_token != original_token:
            # Token was refreshed, notify callback
            updated_credentials = {
                'access_token': self._credentials.token,
                'refresh_token': self._credentials.refresh_token,
                'client_id': self._config.credentials.get('client_id'),
                'client_secret': self._config.credentials.get('client_secret'),
            }

            logger.info(f"Tokens refreshed for {self._config.email_address}")
            self._token_refresh_callback(updated_credentials)

            # Update config
            self._config.credentials.update(updated_credentials)

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

        # List messages (this may trigger token refresh)
        results = self._service.users().messages().list(
            userId='me',
            q=query,
            maxResults=limit
        ).execute()

        # Check if tokens were refreshed during the API call
        await self._check_and_refresh_tokens()

        message_ids = [msg['id'] for msg in results.get('messages', [])]

        # Fetch full message details
        messages = []
        for msg_id in message_ids:
            try:
                msg = await self._fetch_and_parse_message(msg_id)
                if msg:
                    messages.append(msg)
            except Exception as e:
                logger.exception(f"Error fetching Gmail message {msg_id}: {e}")
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

        # Parse timestamp (Gmail internalDate is milliseconds since epoch)
        # Make timezone-aware using UTC
        timestamp = datetime.fromtimestamp(int(msg['internalDate']) / 1000, tz=timezone.utc)

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
        """
        Setup Gmail push notifications using Google Cloud Pub/Sub.

        IMPORTANT: Gmail webhooks require a Google Cloud Pub/Sub topic, not an HTTP callback URL.
        The topic must be pre-configured in Google Cloud Console with proper permissions.

        Args:
            callback_url: For Gmail, this must be a Pub/Sub topic name in the format:
                         projects/{project-id}/topics/{topic-name}
                         NOT an HTTP(S) URL.

        Returns:
            Watch response with historyId and expiration

        Raises:
            ValueError: If callback_url is an HTTP URL instead of Pub/Sub topic
            RuntimeError: If not connected or API call fails

        Setup instructions:
            1. Create a Google Cloud Pub/Sub topic
            2. Grant Gmail API permission to publish to the topic:
               gmail-api-push@system.gserviceaccount.com
            3. Create a push subscription pointing to your HTTP webhook endpoint
            4. Pass the topic name (not the HTTP URL) to this method
        """
        if not self._service:
            raise RuntimeError("Not connected to Gmail API")

        # Validate that callback_url is a Pub/Sub topic, not HTTP URL
        if callback_url.startswith(('http://', 'https://')):
            raise ValueError(
                f"Gmail webhooks require a Google Cloud Pub/Sub topic name, not an HTTP URL. "
                f"Expected format: 'projects/{{project-id}}/topics/{{topic-name}}', "
                f"got: '{callback_url}'. "
                f"See https://developers.google.com/gmail/api/guides/push"
            )

        # Validate Pub/Sub topic format
        if not callback_url.startswith('projects/') or '/topics/' not in callback_url:
            raise ValueError(
                f"Invalid Pub/Sub topic format: '{callback_url}'. "
                f"Expected: 'projects/{{project-id}}/topics/{{topic-name}}'"
            )

        # Setup watch on mailbox
        request = {
            'labelIds': ['INBOX'],
            'topicName': callback_url
        }

        try:
            response = self._service.users().watch(
                userId='me',
                body=request
            ).execute()

            logger.info(f"Gmail webhook setup successful: {response}")
            return response
        except Exception as e:
            raise RuntimeError(
                f"Failed to setup Gmail webhook. Ensure the Pub/Sub topic exists and "
                f"gmail-api-push@system.gserviceaccount.com has Pub/Sub Publisher permissions. "
                f"Error: {e}"
            ) from e

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
