"""Universal email provider protocols and data structures"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, Optional, Any


@dataclass
class EmailMessage:
    """Universal email message structure (provider-agnostic)"""
    message_id: str
    thread_id: Optional[str]
    from_address: str
    to_addresses: list[str]
    subject: str
    timestamp: datetime
    labels: list[str]
    is_read: bool
    is_starred: bool
    has_attachments: bool
    provider_metadata: dict[str, Any]


@dataclass
class EmailProviderConfig:
    """Provider configuration and credentials"""
    provider_type: str  # gmail, outlook, imap
    email_address: str
    credentials: dict[str, Any]  # provider-specific credentials
    connection_params: dict[str, Any] = field(default_factory=dict)  # optional connection parameters

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
    ) -> list[EmailMessage]:
        """
        Fetch messages from provider.

        Args:
            since: Only fetch messages after this timestamp (None = all)
            limit: Maximum number of messages to fetch

        Returns:
            List of EmailMessage objects
        """
        ...

    async def setup_webhook(self, callback_url: str) -> dict[str, Any]:
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
