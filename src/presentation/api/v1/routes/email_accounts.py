"""Email account API endpoints"""

from typing import Annotated

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException,
                     Request, status)
from fastapi.params import Query
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.events.create_event import EventService
from src.infrastructure.external.email.encryption import CredentialEncryptor
from src.infrastructure.external.email.sync import (AuthenticationError,
                                                    UniversalEmailSync)
from src.infrastructure.persistence.models.email_account import EmailAccount
from src.infrastructure.persistence.models.subject import Subject
from src.infrastructure.persistence.models.tenant import Tenant
from src.infrastructure.persistence.repositories.subject_repo import \
    SubjectRepository
from src.presentation.api.dependencies import (get_current_tenant, get_db,
                                               get_db_transactional,
                                               get_event_service_transactional)
from src.presentation.api.v1.schemas.email_account import (
    EmailAccountCreate, EmailAccountResponse, EmailAccountUpdate,
    EmailSyncRequest, EmailSyncResponse, SyncStatusResponse, WebhookSetupRequest)
from src.shared.telemetry.logging import get_logger
from src.shared.utils import utc_now

logger = get_logger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/", response_model=EmailAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_email_account(
    data: EmailAccountCreate,
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """Create a new email account configuration"""
    encryptor = CredentialEncryptor()

    # Create or get subject for this email account
    result = await db.execute(
        select(Subject).where(
            Subject.tenant_id == tenant.id,
            Subject.subject_type == "email_account",
            Subject.external_ref == data.email_address,
        )
    )
    subject = result.scalar_one_or_none()

    if not subject:
        # Create new subject
        subject = Subject(
            tenant_id=tenant.id,
            subject_type="email_account",
            external_ref=data.email_address,
            metadata={"email": data.email_address, "provider": data.provider_type},
        )
        db.add(subject)
        await db.flush()

    # Encrypt credentials
    credentials_encrypted = encryptor.encrypt(data.credentials)

    # Create email account
    email_account = EmailAccount(
        tenant_id=tenant.id,
        subject_id=subject.id,
        provider_type=data.provider_type,
        email_address=data.email_address,
        credentials_encrypted=credentials_encrypted,
        connection_params=data.connection_params,
    )

    db.add(email_account)
    await db.flush()  # Persist to DB and populate auto-generated fields
    await db.refresh(email_account)  # Refresh relationships

    logger.info(
        f"Created email account: {email_account.email_address} "
        f"(provider: {email_account.provider_type})"
    )

    return EmailAccountResponse.model_validate(email_account)


@router.get("/", response_model=list[EmailAccountResponse])
async def list_email_accounts(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max records to return")] = 100,
):
    """List all email accounts for the tenant"""
    result = await db.execute(
        select(EmailAccount).where(EmailAccount.tenant_id == tenant.id).offset(skip).limit(limit)
    )
    accounts = result.scalars().all()
    return [EmailAccountResponse.model_validate(acc) for acc in accounts]


@router.get("/{account_id}", response_model=EmailAccountResponse)
async def get_email_account(
    account_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """Get a specific email account by ID"""
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == account_id, EmailAccount.tenant_id == tenant.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found")

    return EmailAccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=EmailAccountResponse)
async def update_email_account(
    account_id: str,
    data: EmailAccountUpdate,
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """Update email account configuration"""
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == account_id, EmailAccount.tenant_id == tenant.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found")

    # Update fields
    if data.credentials is not None:
        encryptor = CredentialEncryptor()
        account.credentials_encrypted = encryptor.encrypt(data.credentials)

    if data.connection_params is not None:
        account.connection_params = data.connection_params

    if data.is_active is not None:
        account.is_active = data.is_active

    await db.flush()
    await db.refresh(account)

    return EmailAccountResponse.model_validate(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_account(
    account_id: str,
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """Delete email account (soft delete by deactivating)"""
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == account_id, EmailAccount.tenant_id == tenant.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found")

    account.is_active = False


@router.post("/{account_id}/sync", response_model=EmailSyncResponse)
@limiter.limit("10/hour")  # Limit email sync to 10 per hour per IP
async def sync_email_account(
    request: Request,  # Required for slowapi
    account_id: str,
    sync_request: EmailSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    event_service: Annotated[EventService, Depends(get_event_service_transactional)],
):
    """Trigger email sync for account"""
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == account_id, EmailAccount.tenant_id == tenant.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found")

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email account is deactivated",
        )

    # Perform sync
    sync_service = UniversalEmailSync(db, event_service)

    try:
        stats = await sync_service.sync_account(account, incremental=sync_request.incremental)
        return EmailSyncResponse(**stats)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.post("/{account_id}/sync-background", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/hour")  # Limit background sync to 20 per hour per IP
async def sync_email_account_background(
    request: Request,  # Required for slowapi
    account_id: str,
    background_tasks: BackgroundTasks,
    sync_request: EmailSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """
    Trigger email sync in background.

    The sync runs asynchronously while the user continues working.
    Returns immediately with 202 Accepted status.
    """
    # Verify email account exists
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == account_id, EmailAccount.tenant_id == tenant.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found")

    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email account is deactivated",
        )

    # Add sync task to background
    background_tasks.add_task(
        _run_email_sync_background,
        account_id=account_id,
        tenant_id=tenant.id,
        incremental=sync_request.incremental,
    )

    return {
        "message": "Email sync started in background",
        "email_account_id": account_id,
        "email_address": account.email_address,
        "status": "queued",
        "incremental": sync_request.incremental,
    }


async def _run_email_sync_background(account_id: str, tenant_id: str, *, incremental: bool = True) -> None:
    """
    Background task to run email sync with status tracking.

    This runs asynchronously after the HTTP response is sent.
    Updates sync_status fields for progress monitoring.
    """
    # Create new DB session for background task
    from src.application.services.hash_service import HashService
    from src.infrastructure.persistence.database import AsyncSessionLocal
    from src.infrastructure.persistence.repositories.event_repo import \
        EventRepository
    from src.infrastructure.persistence.repositories.event_schema_repo import \
        EventSchemaRepository

    async with AsyncSessionLocal() as db:
        account = None
        try:
            logger.info("Starting background sync for account %s", account_id)

            # Get email account
            result = await db.execute(
                select(EmailAccount).where(
                    EmailAccount.id == account_id, EmailAccount.tenant_id == tenant_id
                )
            )
            account = result.scalar_one_or_none()

            if not account:
                logger.error("Email account %s not found in background task", account_id)
                return

            # Update sync status to running
            account.sync_status = "running"
            account.sync_started_at = utc_now()
            account.sync_error = None
            account.sync_messages_fetched = 0
            account.sync_events_created = 0
            await db.commit()

            # Create services
            event_repo = EventRepository(db)
            schema_repo = EventSchemaRepository(db)
            hash_service = HashService()
            subject_repo = SubjectRepository(db)
            event_service = EventService(event_repo, hash_service, subject_repo, schema_repo)

            # Get progress publisher for real-time updates
            from src.infrastructure.messaging.redis_pubsub import get_sync_publisher
            progress_publisher = get_sync_publisher()

            # Run sync with progress publisher
            sync_service = UniversalEmailSync(db, event_service, progress_publisher)
            stats = await sync_service.sync_account(account, incremental=incremental)

            # Update sync status to completed
            account.sync_status = "completed"
            account.sync_completed_at = utc_now()
            account.sync_messages_fetched = int(stats["messages_fetched"])
            account.sync_events_created = int(stats["events_created"])
            await db.commit()

            logger.info(
                "Background sync completed for %s: %d events created from %d messages",
                account.email_address,
                stats["events_created"],
                stats["messages_fetched"],
            )

        except AuthenticationError as e:
            logger.exception("Authentication failed for account %s: %s", account_id, e)
            if account:
                account.sync_status = "failed"
                account.sync_completed_at = utc_now()
                account.sync_error = f"Authentication failed: {e}"
                await db.commit()

        except Exception as e:
            logger.exception("Background sync failed for account %s: %s", account_id, e)
            if account:
                account.sync_status = "failed"
                account.sync_completed_at = utc_now()
                account.sync_error = str(e)[:500]  # Truncate long errors
                await db.commit()


@router.get("/{account_id}/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(
    account_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
):
    """
    Get the current sync status for an email account.

    Use this endpoint to poll for background sync progress.
    """
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == account_id, EmailAccount.tenant_id == tenant.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found")

    # Calculate duration if we have timestamps
    duration_seconds = None
    if account.sync_started_at:
        end_time = account.sync_completed_at or utc_now()
        duration_seconds = (end_time - account.sync_started_at).total_seconds()

    return SyncStatusResponse(
        account_id=account.id,
        email_address=account.email_address,
        status=account.sync_status,
        started_at=account.sync_started_at,
        completed_at=account.sync_completed_at,
        messages_fetched=account.sync_messages_fetched,
        events_created=account.sync_events_created,
        error=account.sync_error,
        duration_seconds=duration_seconds,
    )


@router.post("/{account_id}/webhook", response_model=dict)
async def setup_webhook(
    account_id: str,
    webhook_request: WebhookSetupRequest,
    db: Annotated[AsyncSession, Depends(get_db_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    event_service: Annotated[EventService, Depends(get_event_service_transactional)],
):
    """Setup webhook for real-time email sync"""
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == account_id, EmailAccount.tenant_id == tenant.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email account not found")

    # Setup webhook
    sync_service = UniversalEmailSync(db, event_service)

    try:
        webhook_config = await sync_service.setup_webhook(account, webhook_request.callback_url)

        # Store webhook ID
        account.webhook_id = webhook_config.get("id") or webhook_config.get("subscriptionId")
        if not account.webhook_id:
            logger.warning("Webhook setup response missing ID: %s", webhook_config)

        return webhook_config

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
