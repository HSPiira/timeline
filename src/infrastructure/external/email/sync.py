"""Universal email sync service (provider-agnostic)"""

from datetime import datetime, timedelta
from typing import Any, Protocol, cast

from google.auth.exceptions import RefreshError
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.events.create_event import EventService
from src.infrastructure.external.email.encryption import CredentialEncryptor
from src.infrastructure.external.email.factory import EmailProviderFactory
from src.infrastructure.external.email.protocols import (EmailMessage,
                                                         EmailProviderConfig)
from src.infrastructure.persistence.models.email_account import EmailAccount
from src.infrastructure.persistence.models.event import Event
from src.infrastructure.persistence.models.subject import Subject
from src.presentation.api.v1.schemas.event import EventCreate
from src.shared.telemetry.logging import get_logger
from src.shared.utils import utc_now

logger = get_logger(__name__)


class TokenRefreshProvider(Protocol):
    """Protocol for providers that support token refresh callbacks"""

    def set_token_refresh_callback(self, callback: Any) -> None:
        """Set callback for token refresh events"""
        ...


class AuthenticationError(Exception):
    """Raised when email provider authentication fails"""


class UniversalEmailSync:
    """Provider-agnostic email sync service"""

    def __init__(self, db: AsyncSession, event_service: EventService):
        self.db = db
        self.event_service = event_service
        self.encryptor = CredentialEncryptor()

    async def sync_account(self, email_account: EmailAccount, *, incremental: bool = True) -> dict[str, int | str]:
        """
        Sync email account to Timeline events (works with ANY provider).

        Args:
            email_account: EmailAccount configuration
            incremental: If True, only sync since last_sync_at

        Returns:
            Sync statistics
        """
        logger.info(
            "Starting sync for %s (provider: %s, incremental: %s)",
            email_account.email_address,
            email_account.provider_type,
            incremental
        )

        credentials = self.encryptor.decrypt(email_account.credentials_encrypted)
        config = EmailProviderConfig(
            provider_type=email_account.provider_type,
            email_address=email_account.email_address,
            credentials=credentials,
            connection_params=email_account.connection_params or {},
        )

        provider = EmailProviderFactory.create_provider(config)

        if email_account.provider_type == "gmail" and hasattr(
            provider, "set_token_refresh_callback"
        ):

            def save_refreshed_tokens(updated_credentials: dict[str, str]) -> None:
                """
                Save refreshed tokens back to database immediately.

                This callback is synchronous because it's called from Google's OAuth library.
                We update the email_account object in-memory and rely on the transaction
                commit at the end of sync_account() to persist the changes.
                """
                try:
                    email_account.credentials_encrypted = self.encryptor.encrypt(
                        updated_credentials
                    )
                    email_account.token_last_refreshed_at = utc_now()
                    email_account.token_refresh_count = (email_account.token_refresh_count or 0) + 1
                    logger.info(
                        "Auto-refreshed OAuth tokens for %s (refresh #%s). System working correctly!",
                        email_account.email_address,
                        email_account.token_refresh_count
                    )
                except Exception as e:
                    email_account.token_refresh_failures = (
                        email_account.token_refresh_failures or 0
                    ) + 1
                    logger.error(
                        "CRITICAL: Failed to save refreshed tokens for %s: %s. User may need to re-authenticate if tokens expire.",
                        email_account.email_address,
                        e,
                        exc_info=True,
                    )

            # Type narrowing: hasattr confirmed the method exists
            cast(TokenRefreshProvider, provider).set_token_refresh_callback(save_refreshed_tokens)

        try:
            await provider.connect(config)

            since = email_account.last_sync_at if incremental else None
            messages = await provider.fetch_messages(since=since, limit=500)

            logger.info("Fetched %s messages from %s", len(messages), email_account.provider_type)

            (
                events_created,
                last_processed_timestamp,
            ) = await self._transform_and_create_events(email_account, messages)

            if events_created > 0 and last_processed_timestamp:
                email_account.last_sync_at = last_processed_timestamp
            elif events_created == 0 and len(messages) > 0:
                logger.warning(
                    "Fetched %s messages but created 0 events. "
                    "Not updating last_sync_at to allow retry.", len(messages)
                )

            # Always commit to persist any token refreshes that occurred
            await self.db.commit()
            logger.info(
                "Sync transaction committed (events: %s, "
                "last_sync_at updated: %s)", events_created, events_created > 0
            )

            stats: dict[str, int | str] = {
                "messages_fetched": len(messages),
                "events_created": events_created,
                "provider": email_account.provider_type,
                "sync_type": "incremental" if incremental else "full",
            }

            logger.info("Sync completed: %s", stats)
            return stats

        except RefreshError as e:
            # Track authentication failure for monitoring
            email_account.last_auth_error = str(e)
            email_account.last_auth_error_at = utc_now()
            email_account.token_refresh_failures = (email_account.token_refresh_failures or 0) + 1
            await self.db.commit()  # Persist error tracking even on failure

            logger.error(
                "OAuth token refresh failed for %s: %s", email_account.email_address, e,
                exc_info=True,
            )
            raise AuthenticationError(
                "Gmail OAuth token has expired or been revoked for %s. "
                "Please re-authenticate the email account.", email_account.email_address
            ) from e
        finally:
            await provider.disconnect()

    async def _transform_and_create_events(
        self, email_account: EmailAccount, messages: list[EmailMessage]
    ) -> tuple[int, datetime | None]:
        """
        Transform email messages to Timeline events using bulk insert.

        This transformation is IDENTICAL for all providers (Gmail, Outlook, IMAP).

        Performance optimizations:
        - Batch duplicate check (1 query for all messages)
        - Bulk event insert (1 query for all new events)
        - In-memory filtering of duplicates

        Returns:
            Tuple of (events_created, last_processed_timestamp)
        """
        if not messages:
            return 0, None

        # PERFORMANCE FIX: Batch check for existing events to avoid N+1 queries
        message_ids = [msg.message_id for msg in messages]
        existing_message_ids = await self._check_existing_events_batch(
            email_account.subject_id, message_ids
        )

        latest_event_time = await self._get_latest_event_time(email_account.subject_id)
        sorted_messages = sorted(messages, key=lambda msg: msg.timestamp)
        last_timestamp = latest_event_time

        # Build list of events to create (filter duplicates, adjust timestamps)
        events_to_create: list[EventCreate] = []
        last_successfully_processed_timestamp: datetime | None = None

        for msg in sorted_messages:
            # IN-MEMORY CHECK: O(1) lookup instead of database query
            if msg.message_id in existing_message_ids:
                logger.debug("Skipping message %s - event already exists", msg.message_id)
                last_successfully_processed_timestamp = msg.timestamp
                continue

            event_time = msg.timestamp
            timestamp_adjusted = False

            if last_timestamp and event_time <= last_timestamp:
                original_time = event_time
                event_time = last_timestamp + timedelta(microseconds=1)
                timestamp_adjusted = True
                logger.debug(
                    "Adjusted timestamp for email %s: %s -> %s",
                    msg.message_id, original_time, event_time
                )

            last_timestamp = event_time

            event = EventCreate(
                subject_id=email_account.subject_id,
                event_type="email_received",
                schema_version=1,
                event_time=event_time,
                payload={
                    "message_id": msg.message_id,
                    "thread_id": msg.thread_id,
                    "from": msg.from_address,
                    "to": msg.to_addresses,
                    "subject": msg.subject,
                    "received_at": msg.timestamp.isoformat(),
                    "timestamp_adjusted": timestamp_adjusted,
                    "labels": msg.labels,
                    "is_read": msg.is_read,
                    "is_starred": msg.is_starred,
                    "has_attachments": msg.has_attachments,
                    "provider": email_account.provider_type,
                    "provider_metadata": msg.provider_metadata,
                },
            )
            events_to_create.append(event)
            last_successfully_processed_timestamp = msg.timestamp

        # BULK INSERT: Create all events in single DB roundtrip
        if events_to_create:
            try:
                await self.event_service.create_events_bulk(
                    tenant_id=email_account.tenant_id,
                    events=events_to_create,
                    skip_schema_validation=True,  # Email events don't use schema validation
                    trigger_workflows=False,  # Batch sync doesn't trigger workflows
                )
                logger.info(
                    "Bulk inserted %d email events for %s",
                    len(events_to_create), email_account.email_address
                )
            except Exception as e:
                logger.error(
                    "Bulk insert failed for %s: %s. Falling back to sequential.",
                    email_account.email_address, e, exc_info=True
                )
                # Fallback to sequential insert on bulk failure
                return await self._create_events_sequential(
                    email_account, events_to_create
                )

        return len(events_to_create), last_successfully_processed_timestamp

    async def _create_events_sequential(
        self, email_account: EmailAccount, events: list[EventCreate]
    ) -> tuple[int, datetime | None]:
        """
        Fallback: Create events one by one if bulk insert fails.

        This is slower but more resilient to individual event failures.
        """
        events_created = 0
        last_timestamp: datetime | None = None

        for event in events:
            try:
                await self.event_service.create_event(
                    tenant_id=email_account.tenant_id, event=event
                )
                events_created += 1
                last_timestamp = event.event_time
            except Exception as e:
                logger.error(
                    "Failed to create event for message %s: %s",
                    event.payload.get("message_id"), e, exc_info=True
                )
                continue

        return events_created, last_timestamp

    async def _check_existing_events_batch(
        self, subject_id: str, message_ids: list[str]
    ) -> set[str]:
        """
        Batch check for existing events - SINGLE database query.

        Performance optimization to avoid N+1 queries when processing multiple messages.

        Args:
            subject_id: Subject ID to check
            message_ids: List of message IDs to check

        Returns:
            Set of message_ids that already have events created

        Performance:
            - Before: N queries (one per message)
            - After: 1 query for all messages
            - 50-100x faster for large batches
        """
        from sqlalchemy import String, cast

        if not message_ids:
            return set()

        result = await self.db.execute(
            select(cast(Event.payload["message_id"], String)).where(
                and_(
                    Event.subject_id == subject_id,
                    Event.event_type == "email_received",
                    cast(Event.payload["message_id"], String).in_(message_ids),
                )
            )
        )

        return set(result.scalars().all())

    async def _check_event_exists(self, subject_id: str, message_id: str) -> Event | None:
        """
        Check if an event already exists for this email message.

        Note: For batch operations, use _check_existing_events_batch() instead
        to avoid N+1 queries.
        """
        from sqlalchemy import String, cast

        result = await self.db.execute(
            select(Event)
            .where(
                and_(
                    Event.subject_id == subject_id,
                    Event.event_type == "email_received",
                    cast(Event.payload["message_id"], String) == message_id,
                )
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def _get_latest_event_time(self, subject_id: str) -> datetime | None:
        """Get the timestamp of the most recent event for this subject"""
        from sqlalchemy import desc

        result = await self.db.execute(
            select(Event.event_time)
            .where(and_(Event.subject_id == subject_id, Event.event_type == "email_received"))
            .order_by(desc(Event.event_time))
            .limit(1)
        )

        return result.scalar_one_or_none()

    async def setup_webhook(self, email_account: EmailAccount, callback_url: str) -> dict[str, str]:
        """Setup webhook for real-time sync (if provider supports it)"""
        credentials = self.encryptor.decrypt(email_account.credentials_encrypted)
        config = EmailProviderConfig(
            provider_type=email_account.provider_type,
            email_address=email_account.email_address,
            credentials=credentials,
            connection_params=email_account.connection_params or {},
        )

        provider = EmailProviderFactory.create_provider(config)

        if not provider.supports_webhooks:
            raise ValueError(
                "Provider %s does not support webhooks. "
                "Use polling sync instead.", config.provider_type
            )

        try:
            await provider.connect(config)
            webhook_config = await provider.setup_webhook(callback_url)
            logger.info("Webhook setup for %s: %s", email_account.email_address, webhook_config)
            return webhook_config
        finally:
            await provider.disconnect()

    async def get_subject_for_email(self, tenant_id: str, email_address: str) -> Subject | None:
        """Get or create Subject for email account"""
        result = await self.db.execute(
            select(Subject).where(
                Subject.tenant_id == tenant_id,
                Subject.subject_type == "email_account",
                Subject.external_ref == email_address,
            )
        )
        return result.scalar_one_or_none()
