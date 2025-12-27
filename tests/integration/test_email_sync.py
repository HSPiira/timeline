"""Integration tests for email synchronization"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from integrations.email.sync import UniversalEmailSync, AuthenticationError
from integrations.email.protocols import EmailMessage, EmailProviderType
from models.email_account import EmailAccount
from models.subject import Subject
from repositories.event_repo import EventRepository


@pytest.fixture
async def test_email_account(test_db, test_tenant):
    """Create test email account"""
    # Create subject for email account
    subject = Subject(
        id="email-subject-id",
        tenant_id=test_tenant.id,
        subject_type="email_account",
        external_ref="test@example.com"
    )
    test_db.add(subject)
    await test_db.flush()

    # Create email account
    account = EmailAccount(
        id="account-123",
        tenant_id=test_tenant.id,
        subject_id=subject.id,
        provider_type=EmailProviderType.GMAIL,
        email_address="test@example.com",
        credentials_encrypted="encrypted_credentials",
        is_active=True
    )
    test_db.add(account)
    await test_db.commit()
    await test_db.refresh(account)
    return account


@pytest.fixture
def mock_email_messages():
    """Create mock email messages"""
    return [
        EmailMessage(
            message_id="msg1",
            thread_id="thread1",
            from_address="sender1@example.com",
            to_addresses=["test@example.com"],
            subject="Test Email 1",
            timestamp=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            labels=["INBOX"],
            is_read=False,
            is_starred=False,
            has_attachments=False,
            provider_metadata={}
        ),
        EmailMessage(
            message_id="msg2",
            thread_id="thread2",
            from_address="sender2@example.com",
            to_addresses=["test@example.com"],
            subject="Test Email 2",
            timestamp=datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            labels=["INBOX", "IMPORTANT"],
            is_read=True,
            is_starred=True,
            has_attachments=True,
            provider_metadata={"size": 1024}
        ),
    ]


@pytest.mark.asyncio
async def test_gmail_sync_creates_events(test_db, test_email_account, mock_email_messages):
    """Test that Gmail sync creates events correctly"""
    from services.event_service import EventService
    from services.hash_service import HashService
    from repositories.subject_repo import SubjectRepository
    from repositories.event_schema_repo import EventSchemaRepository

    # Create event service
    event_service = EventService(
        event_repo=EventRepository(test_db),
        hash_service=HashService(),
        subject_repo=SubjectRepository(test_db),
        schema_repo=EventSchemaRepository(test_db)
    )

    # Create sync service
    sync_service = UniversalEmailSync(test_db, event_service)

    # Mock the provider
    with patch('integrations.email.factory.EmailProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock()
        mock_provider.connect = AsyncMock()
        mock_provider.fetch_messages = AsyncMock(return_value=mock_email_messages)
        mock_provider.disconnect = AsyncMock()
        mock_factory.return_value = mock_provider

        # Mock the encryptor
        with patch('integrations.email.sync.CredentialEncryptor') as mock_encryptor_class:
            mock_encryptor = MagicMock()
            mock_encryptor.decrypt.return_value = {"access_token": "test_token"}
            mock_encryptor_class.return_value = mock_encryptor

            # Run sync
            stats = await sync_service.sync_account(test_email_account, incremental=True)

            # Verify stats
            assert stats['messages_fetched'] == 2
            assert stats['events_created'] == 2
            assert stats['provider'] == EmailProviderType.GMAIL
            assert stats['sync_type'] == 'incremental'

            # Verify events were created
            event_repo = EventRepository(test_db)
            events = await event_repo.get_by_subject(
                test_email_account.subject_id,
                test_email_account.tenant_id
            )

            assert len(events) == 2

            # Verify event details (most recent first due to desc ordering)
            event1 = events[0]  # msg2
            assert event1.event_type == "email_received"
            assert event1.payload["message_id"] == "msg2"
            assert event1.payload["subject"] == "Test Email 2"
            assert event1.payload["from"] == "sender2@example.com"
            assert event1.payload["is_starred"] is True
            assert event1.payload["has_attachments"] is True

            event2 = events[1]  # msg1
            assert event2.payload["message_id"] == "msg1"
            assert event2.payload["subject"] == "Test Email 1"


@pytest.mark.asyncio
async def test_email_sync_deduplication(test_db, test_email_account, mock_email_messages):
    """Test that duplicate emails are not synced twice"""
    from services.event_service import EventService
    from services.hash_service import HashService
    from repositories.subject_repo import SubjectRepository
    from repositories.event_schema_repo import EventSchemaRepository

    event_service = EventService(
        event_repo=EventRepository(test_db),
        hash_service=HashService(),
        subject_repo=SubjectRepository(test_db),
        schema_repo=EventSchemaRepository(test_db)
    )

    sync_service = UniversalEmailSync(test_db, event_service)

    with patch('integrations.email.factory.EmailProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock()
        mock_provider.connect = AsyncMock()
        mock_provider.fetch_messages = AsyncMock(return_value=mock_email_messages)
        mock_provider.disconnect = AsyncMock()
        mock_factory.return_value = mock_provider

        with patch('integrations.email.sync.CredentialEncryptor') as mock_encryptor_class:
            mock_encryptor = MagicMock()
            mock_encryptor.decrypt.return_value = {"access_token": "test_token"}
            mock_encryptor_class.return_value = mock_encryptor

            # First sync
            stats1 = await sync_service.sync_account(test_email_account)
            assert stats1['events_created'] == 2

            # Second sync with same messages - should use batch deduplication
            stats2 = await sync_service.sync_account(test_email_account)
            assert stats2['events_created'] == 0  # No duplicates created
            assert stats2['messages_fetched'] == 2  # Still fetched messages

            # Verify only 2 events total
            event_repo = EventRepository(test_db)
            events = await event_repo.get_by_subject(
                test_email_account.subject_id,
                test_email_account.tenant_id
            )
            assert len(events) == 2


@pytest.mark.asyncio
async def test_email_sync_batch_deduplication_performance(
    test_db, test_email_account
):
    """Test that batch deduplication is used (N+1 query fix)"""
    from services.event_service import EventService
    from services.hash_service import HashService
    from repositories.subject_repo import SubjectRepository
    from repositories.event_schema_repo import EventSchemaRepository

    # Create 100 mock messages
    messages = [
        EmailMessage(
            message_id=f"msg{i}",
            thread_id=f"thread{i}",
            from_address=f"sender{i}@example.com",
            to_addresses=["test@example.com"],
            subject=f"Email {i}",
            timestamp=datetime(2025, 1, 1, 10, 0, i, tzinfo=timezone.utc),
            labels=["INBOX"],
            is_read=False,
            is_starred=False,
            has_attachments=False,
            provider_metadata={}
        )
        for i in range(100)
    ]

    event_service = EventService(
        event_repo=EventRepository(test_db),
        hash_service=HashService(),
        subject_repo=SubjectRepository(test_db),
        schema_repo=EventSchemaRepository(test_db)
    )

    sync_service = UniversalEmailSync(test_db, event_service)

    with patch('integrations.email.factory.EmailProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock()
        mock_provider.connect = AsyncMock()
        mock_provider.fetch_messages = AsyncMock(return_value=messages)
        mock_provider.disconnect = AsyncMock()
        mock_factory.return_value = mock_provider

        with patch('integrations.email.sync.CredentialEncryptor') as mock_encryptor_class:
            mock_encryptor = MagicMock()
            mock_encryptor.decrypt.return_value = {"access_token": "test_token"}
            mock_encryptor_class.return_value = mock_encryptor

            # Spy on _check_existing_events_batch to ensure it's called
            original_batch_check = sync_service._check_existing_events_batch
            batch_check_called = False

            async def spy_batch_check(*args, **kwargs):
                nonlocal batch_check_called
                batch_check_called = True
                return await original_batch_check(*args, **kwargs)

            sync_service._check_existing_events_batch = spy_batch_check

            # Run sync
            stats = await sync_service.sync_account(test_email_account)

            # Verify batch check was used
            assert batch_check_called, "Batch deduplication method should be called"
            assert stats['events_created'] == 100


@pytest.mark.asyncio
async def test_email_sync_handles_auth_error(test_db, test_email_account):
    """Test that authentication errors are properly handled"""
    from services.event_service import EventService
    from services.hash_service import HashService
    from repositories.subject_repo import SubjectRepository
    from repositories.event_schema_repo import EventSchemaRepository
    from google.auth.exceptions import RefreshError

    event_service = EventService(
        event_repo=EventRepository(test_db),
        hash_service=HashService(),
        subject_repo=SubjectRepository(test_db),
        schema_repo=EventSchemaRepository(test_db)
    )

    sync_service = UniversalEmailSync(test_db, event_service)

    with patch('integrations.email.factory.EmailProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock()
        mock_provider.connect = AsyncMock(side_effect=RefreshError("Token expired"))
        mock_provider.disconnect = AsyncMock()
        mock_factory.return_value = mock_provider

        with patch('integrations.email.sync.CredentialEncryptor') as mock_encryptor_class:
            mock_encryptor = MagicMock()
            mock_encryptor.decrypt.return_value = {"access_token": "expired_token"}
            mock_encryptor_class.return_value = mock_encryptor

            # Should raise AuthenticationError
            with pytest.raises(AuthenticationError, match="OAuth token has expired"):
                await sync_service.sync_account(test_email_account)

            # Verify error was tracked
            await test_db.refresh(test_email_account)
            assert test_email_account.last_auth_error is not None
            assert test_email_account.token_refresh_failures == 1


@pytest.mark.asyncio
async def test_incremental_vs_full_sync(test_db, test_email_account, mock_email_messages):
    """Test difference between incremental and full sync"""
    from services.event_service import EventService
    from services.hash_service import HashService
    from repositories.subject_repo import SubjectRepository
    from repositories.event_schema_repo import EventSchemaRepository

    event_service = EventService(
        event_repo=EventRepository(test_db),
        hash_service=HashService(),
        subject_repo=SubjectRepository(test_db),
        schema_repo=EventSchemaRepository(test_db)
    )

    sync_service = UniversalEmailSync(test_db, event_service)

    with patch('integrations.email.factory.EmailProviderFactory.create_provider') as mock_factory:
        mock_provider = AsyncMock()
        mock_provider.connect = AsyncMock()
        mock_provider.disconnect = AsyncMock()

        # Track fetch_messages calls
        fetch_calls = []

        async def track_fetch(since=None, limit=100):
            fetch_calls.append({"since": since, "limit": limit})
            return mock_email_messages

        mock_provider.fetch_messages = track_fetch
        mock_factory.return_value = mock_provider

        with patch('integrations.email.sync.CredentialEncryptor') as mock_encryptor_class:
            mock_encryptor = MagicMock()
            mock_encryptor.decrypt.return_value = {"access_token": "test_token"}
            mock_encryptor_class.return_value = mock_encryptor

            # Full sync (incremental=False)
            await sync_service.sync_account(test_email_account, incremental=False)
            assert fetch_calls[-1]["since"] is None  # No since parameter

            # Incremental sync (incremental=True)
            await sync_service.sync_account(test_email_account, incremental=True)
            assert fetch_calls[-1]["since"] is not None  # Should use last_sync_at
