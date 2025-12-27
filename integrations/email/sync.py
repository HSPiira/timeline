"""Universal email sync service (provider-agnostic)"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from integrations.email.protocols import IEmailProvider, EmailProviderConfig, EmailMessage
from integrations.email.factory import EmailProviderFactory
from integrations.email.encryption import CredentialEncryptor
from models.email_account import EmailAccount
from models.subject import Subject
from services.event_service import EventService
from schemas.event import EventCreate
from core.logging import get_logger

logger = get_logger(__name__)


class UniversalEmailSync:
    """Provider-agnostic email sync service"""

    def __init__(
        self,
        db: AsyncSession,
        event_service: EventService
    ):
        self.db = db
        self.event_service = event_service
        self.encryptor = CredentialEncryptor()

    async def sync_account(
        self,
        email_account: EmailAccount,
        incremental: bool = True
    ) -> dict:
        """
        Sync email account to Timeline events (works with ANY provider).

        Args:
            email_account: EmailAccount configuration
            incremental: If True, only sync since last_sync_at

        Returns:
            Sync statistics
        """
        logger.info(
            f"Starting sync for {email_account.email_address} "
            f"(provider: {email_account.provider_type}, incremental: {incremental})"
        )

        # 1. Build provider config
        credentials = self.encryptor.decrypt(email_account.credentials_encrypted)
        config = EmailProviderConfig(
            provider_type=email_account.provider_type,
            email_address=email_account.email_address,
            credentials=credentials,
            connection_params=email_account.connection_params or {}
        )

        # 2. Create provider (Gmail, Outlook, IMAP, etc.)
        provider = EmailProviderFactory.create_provider(config)

        try:
            # 3. Connect to provider
            await provider.connect(config)

            # 4. Fetch messages
            since = email_account.last_sync_at if incremental else None
            messages = await provider.fetch_messages(since=since, limit=100)

            logger.info(f"Fetched {len(messages)} messages from {email_account.provider_type}")

            # 5. Transform to Timeline events (UNIVERSAL - same for all providers)
            events_created = await self._transform_and_create_events(
                email_account, messages
            )

            # 6. Update last sync timestamp
            email_account.last_sync_at = datetime.utcnow()
            await self.db.commit()

            stats = {
                'messages_fetched': len(messages),
                'events_created': events_created,
                'provider': email_account.provider_type,
                'sync_type': 'incremental' if incremental else 'full'
            }

            logger.info(f"Sync completed: {stats}")
            return stats

        finally:
            # 7. Disconnect
            await provider.disconnect()

    async def _transform_and_create_events(
        self,
        email_account: EmailAccount,
        messages: List[EmailMessage]
    ) -> int:
        """
        Transform email messages to Timeline events.

        This transformation is IDENTICAL for all providers (Gmail, Outlook, IMAP).
        """
        events_created = 0

        for msg in messages:
            try:
                # Create email_received event
                event = EventCreate(
                    subject_id=email_account.subject_id,
                    event_type='email_received',
                    event_time=msg.timestamp,
                    payload={
                        'message_id': msg.message_id,
                        'thread_id': msg.thread_id,
                        'from': msg.from_address,
                        'to': msg.to_addresses,
                        'subject': msg.subject,
                        'labels': msg.labels,
                        'is_read': msg.is_read,
                        'is_starred': msg.is_starred,
                        'has_attachments': msg.has_attachments,
                        'provider': email_account.provider_type,
                        'provider_metadata': msg.provider_metadata
                    }
                )

                await self.event_service.create_event(
                    tenant_id=email_account.tenant_id,
                    event=event
                )

                events_created += 1

            except Exception as e:
                logger.error(
                    f"Failed to create event for message {msg.message_id}: {e}",
                    exc_info=True
                )
                continue

        return events_created

    async def setup_webhook(
        self,
        email_account: EmailAccount,
        callback_url: str
    ) -> dict:
        """
        Setup webhook for real-time sync (if provider supports it).

        Args:
            email_account: EmailAccount configuration
            callback_url: URL to receive webhook notifications

        Returns:
            Webhook configuration details
        """
        # Build provider config
        credentials = self.encryptor.decrypt(email_account.credentials_encrypted)
        config = EmailProviderConfig(
            provider_type=email_account.provider_type,
            email_address=email_account.email_address,
            credentials=credentials,
            connection_params=email_account.connection_params or {}
        )

        # Create provider
        provider = EmailProviderFactory.create_provider(config)

        if not provider.supports_webhooks:
            raise ValueError(
                f"Provider {email_account.provider_type} does not support webhooks. "
                "Use polling sync instead."
            )

        try:
            await provider.connect(config)
            webhook_config = await provider.setup_webhook(callback_url)
            logger.info(f"Webhook setup for {email_account.email_address}: {webhook_config}")
            return webhook_config
        finally:
            await provider.disconnect()

    async def get_subject_for_email(
        self,
        tenant_id: str,
        email_address: str
    ) -> Optional[Subject]:
        """Get or create Subject for email account"""
        result = await self.db.execute(
            select(Subject).where(
                Subject.tenant_id == tenant_id,
                Subject.subject_type == 'email_account',
                Subject.external_id == email_address
            )
        )
        return result.scalar_one_or_none()
