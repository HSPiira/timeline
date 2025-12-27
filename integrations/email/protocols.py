"""Universal email provider protocols and data structures"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Optional, List, Dict, Any


@dataclass
class EmailMessage:
    """Universal email message structure (provider-agnostic)"""
    message_id: str
    thread_id: Optional[str]
    from_address: str
    to_addresses: List[str]
    subject: str
    timestamp: datetime
    labels: List[str]
    is_read: bool
    is_starred: bool
    has_attachments: bool
    provider_metadata: Dict[str, Any]


@dataclass
class EmailProviderConfig:
    """Provider configuration and credentials"""
    provider_type: str  # gmail, outlook, imap
    email_address: str
    credentials: Dict[str, Any]  # provider-specific credentials
    connection_params: Dict[str, Any] = None  # optional connection parameters

    def __post_init__(self):
        if self.connection_params is None:
            self.connection_params = {}


class IEmailProvider(Protocol):
    """Universal email provider interface (Dependency Inversion Principle)"""

    async def connect(self, config: EmailProviderConfig) -> None:
        """Establish connection to email provider"""
        ...

    async def disconnect(self) -> None:
        """Close connection to email provider"""
        ...

    async def fetch_messages(
        self,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[EmailMessage]:
        """
        Fetch messages from provider.

        Args:
            since: Only fetch messages after this timestamp (None = all)
            limit: Maximum number of messages to fetch

        Returns:
            List of EmailMessage objects
        """
        ...

    async def setup_webhook(self, callback_url: str) -> Dict[str, Any]:
        """
        Setup webhook/push notifications for real-time sync.

        Args:
            callback_url: URL to receive webhook notifications

        Returns:
            Webhook configuration details
        """
        ...

    async def remove_webhook(self) -> None:
        """Remove webhook/push notifications"""
        ...

    @property
    def supports_webhooks(self) -> bool:
        """Whether this provider supports webhooks"""
        ...

    @property
    def supports_incremental_sync(self) -> bool:
        """Whether this provider supports incremental sync"""
        ...
