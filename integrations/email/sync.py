"""Universal email sync service (provider-agnostic)"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from integrations.email.protocols import IEmailProvider, EmailProviderConfig, EmailMessage
from integrations.email.factory import EmailProviderFactory
from integrations.email.encryption import CredentialEncryptor
from models.email_account import EmailAccount
from models.subject import Subject
from models.event import Event
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

        # 3. Set up token refresh callback for Gmail
        if email_account.provider_type == 'gmail' and hasattr(provider, 'set_token_refresh_callback'):
            def save_refreshed_tokens(updated_credentials: dict):
                """Save refreshed tokens back to database"""
                try:
                    email_account.credentials_encrypted = self.encryptor.encrypt(updated_credentials)
                    logger.info(f"Saved refreshed tokens for {email_account.email_address}")
                except Exception as e:
                    logger.error(f"Failed to save refreshed tokens: {e}", exc_info=True)

            provider.set_token_refresh_callback(save_refreshed_tokens)

        try:
            # 4. Connect to provider
            await provider.connect(config)

            # 4. Fetch messages
            since = email_account.last_sync_at if incremental else None
            messages = await provider.fetch_messages(since=since, limit=100)

            logger.info(f"Fetched {len(messages)} messages from {email_account.provider_type}")

            # 5. Transform to Timeline events (UNIVERSAL - same for all providers)
            events_created, last_processed_timestamp = await self._transform_and_create_events(
                email_account, messages
            )

            # 6. Update last sync timestamp ONLY if we successfully processed events
            # Use the timestamp of the most recent email processed, not current time
            # This ensures failed events can be retried on the next sync
            if events_created > 0 and last_processed_timestamp:
                # Strip timezone before saving (database column is timezone-naive)
                # All timestamps are UTC, so we just remove the timezone info
                email_account.last_sync_at = last_processed_timestamp.replace(tzinfo=None)
                await self.db.commit()
                logger.info(f"Updated last_sync_at to {last_processed_timestamp}")
            elif events_created == 0 and len(messages) > 0:
                # No events created but messages were fetched - don't update timestamp
                # This allows retry on next sync
                logger.warning(
                    f"Fetched {len(messages)} messages but created 0 events. "
                    f"Not updating last_sync_at to allow retry."
                )

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
    ) -> tuple[int, Optional[datetime]]:
        """
        Transform email messages to Timeline events.

        This transformation is IDENTICAL for all providers (Gmail, Outlook, IMAP).

        Returns:
            Tuple of (events_created, last_processed_timestamp)
        """
        events_created = 0
        last_successfully_processed_timestamp = None

        # Get the timestamp of the latest event to handle backfilling
        # For old emails, we'll adjust timestamps to maintain temporal ordering
        latest_event_time = await self._get_latest_event_time(email_account.subject_id)

        # Sort messages chronologically (oldest first) to maintain event chain ordering
        # The event service validates that new events have timestamps after previous events
        sorted_messages = sorted(messages, key=lambda msg: msg.timestamp)

        # Track last timestamp to handle duplicates
        from datetime import timedelta
        last_timestamp = latest_event_time  # Start from latest event time if exists

        for msg in sorted_messages:
            try:
                # Check if event already exists for this message_id (deduplication)
                # This makes sync idempotent - safe to retry without creating duplicates
                existing_event = await self._check_event_exists(
                    email_account.subject_id,
                    msg.message_id
                )

                if existing_event:
                    logger.debug(
                        f"Skipping message {msg.message_id} - event already exists (id: {existing_event.id})"
                    )
                    # Still track this as successfully processed to update last_sync_at
                    last_successfully_processed_timestamp = msg.timestamp
                    continue

                # Determine event time - handle backfilling of old emails
                # For emails older than latest event, we adjust the timestamp to maintain temporal ordering
                # The original timestamp is preserved in payload.received_at
                event_time = msg.timestamp
                timestamp_adjusted = False

                if last_timestamp and event_time <= last_timestamp:
                    # Email is older than or equal to latest event
                    # Adjust to 1 microsecond after the last timestamp
                    original_time = event_time
                    event_time = last_timestamp + timedelta(microseconds=1)
                    timestamp_adjusted = True
                    logger.warning(
                        f"Adjusted timestamp for historical email {msg.message_id}: "
                        f"{original_time} -> {event_time} (original preserved in payload)"
                    )

                last_timestamp = event_time

                # Create email_received event
                # TODO: Query active schema version from database instead of hardcoding
                event = EventCreate(
                    subject_id=email_account.subject_id,
                    event_type='email_received',
                    schema_version=1,  # Using v1 for email_received events
                    event_time=event_time,
                    payload={
                        'message_id': msg.message_id,
                        'thread_id': msg.thread_id,
                        'from': msg.from_address,
                        'to': msg.to_addresses,
                        'subject': msg.subject,
                        'received_at': msg.timestamp.isoformat(),  # Original email timestamp
                        'timestamp_adjusted': timestamp_adjusted,  # Flag to indicate adjustment
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
                # Track the timestamp of the last successfully processed email
                # Use the original message timestamp, not the adjusted one
                last_successfully_processed_timestamp = msg.timestamp

            except Exception as e:
                logger.error(
                    f"Failed to create event for message {msg.message_id}: {e}",
                    exc_info=True
                )
                continue

        return events_created, last_successfully_processed_timestamp

    async def _check_event_exists(
        self,
        subject_id: str,
        message_id: str
    ) -> Optional[Event]:
        """
        Check if an event already exists for this email message.

        Uses message_id from payload for deduplication.
        This makes sync idempotent - can safely retry without creating duplicates.

        Args:
            subject_id: Email account subject ID
            message_id: Email message ID from provider

        Returns:
            Event if exists, None otherwise
        """
        from sqlalchemy import cast, String

        # Query for email_received events with matching message_id in payload
        # Use cast to extract text value from JSONB
        result = await self.db.execute(
            select(Event).where(
                and_(
                    Event.subject_id == subject_id,
                    Event.event_type == 'email_received',
                    cast(Event.payload['message_id'], String) == message_id
                )
            ).limit(1)
        )

        return result.scalar_one_or_none()

    async def _get_latest_event_time(
        self,
        subject_id: str
    ) -> Optional[datetime]:
        """
        Get the timestamp of the most recent event for this subject.

        This is used to enforce temporal ordering - we skip emails older than
        the latest event to prevent validation errors.

        Args:
            subject_id: Email account subject ID

        Returns:
            Timestamp of latest event, or None if no events exist
        """
        from sqlalchemy import desc

        result = await self.db.execute(
            select(Event.event_time)
            .where(
                and_(
                    Event.subject_id == subject_id,
                    Event.event_type == 'email_received'
                )
            )
            .order_by(desc(Event.event_time))
            .limit(1)
        )

        return result.scalar_one_or_none()

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
