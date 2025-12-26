# Background Email Sync Guide

Complete guide for implementing background email synchronization.

## Overview

Three approaches for background sync:
1. **FastAPI Background Tasks** - Simple, in-process (best for user-triggered sync)
2. **APScheduler** - Scheduled periodic sync (best for automatic sync)
3. **Celery** - Full task queue (best for production/scale)

---

## Option 1: FastAPI Background Tasks (Recommended for Start)

### Use Case
- User triggers sync manually
- Sync runs in background
- User continues working
- No external dependencies

### Implementation

#### 1. Add Background Sync Endpoint

```python
# api/email_accounts.py

from fastapi import BackgroundTasks

@router.post("/{email_account_id}/sync-background", status_code=status.HTTP_202_ACCEPTED)
async def sync_email_account_background(
    email_account_id: str,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    event_service: Annotated[EventService, Depends(get_event_service_transactional)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """
    Trigger email sync in background.

    Returns immediately while sync runs in background.
    """
    # Get email account
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == email_account_id,
            EmailAccount.tenant_id == tenant.id
        )
    )
    email_account = result.scalar_one_or_none()

    if not email_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found"
        )

    # Add sync task to background
    background_tasks.add_task(
        run_email_sync,
        email_account_id=email_account_id,
        tenant_id=tenant.id
    )

    return {
        "message": "Email sync started in background",
        "email_account_id": email_account_id,
        "status": "queued"
    }


async def run_email_sync(email_account_id: str, tenant_id: str):
    """Background task to run email sync"""
    # Create new DB session for background task
    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            # Get email account
            result = await db.execute(
                select(EmailAccount).where(
                    EmailAccount.id == email_account_id,
                    EmailAccount.tenant_id == tenant_id
                )
            )
            email_account = result.scalar_one_or_none()

            if not email_account:
                logger.error(f"Email account {email_account_id} not found")
                return

            # Create event service
            from repositories.event_repo import EventRepository
            from repositories.event_schema_repo import EventSchemaRepository
            from services.hash_service import HashService

            event_repo = EventRepository(db)
            schema_repo = EventSchemaRepository(db)
            hash_service = HashService()
            event_service = EventService(event_repo, schema_repo, hash_service)

            # Run sync
            sync_service = UniversalEmailSync(db, event_service)
            stats = await sync_service.sync_account(email_account)

            logger.info(f"Background sync completed: {stats}")

        except Exception as e:
            logger.error(f"Background sync failed: {e}", exc_info=True)
```

#### 2. Usage

```bash
# Start sync in background
POST /email-accounts/{id}/sync-background

# Returns immediately
{
  "message": "Email sync started in background",
  "email_account_id": "abc123",
  "status": "queued"
}

# User continues working while sync runs
```

---

## Option 2: Scheduled Periodic Sync (APScheduler)

### Use Case
- Automatic sync every X minutes
- Runs without user intervention
- No external dependencies

### Implementation

#### 1. Install APScheduler

```bash
pip install apscheduler
```

#### 2. Create Background Scheduler

```python
# services/email_scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from datetime import datetime

from core.database import AsyncSessionLocal
from models.email_account import EmailAccount
from integrations.email.sync import UniversalEmailSync
from services.event_service import EventService
from repositories.event_repo import EventRepository
from repositories.event_schema_repo import EventSchemaRepository
from services.hash_service import HashService
from core.logging import get_logger

logger = get_logger(__name__)


class EmailSyncScheduler:
    """Scheduler for automatic email synchronization"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self):
        """Start the scheduler"""
        # Sync all active accounts every 15 minutes
        self.scheduler.add_job(
            self.sync_all_accounts,
            trigger=IntervalTrigger(minutes=15),
            id='sync_all_email_accounts',
            name='Sync all active email accounts',
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("Email sync scheduler started (15 min intervals)")

    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Email sync scheduler stopped")

    async def sync_all_accounts(self):
        """Sync all active email accounts"""
        logger.info("Starting scheduled email sync for all accounts")

        async with AsyncSessionLocal() as db:
            try:
                # Get all active email accounts
                result = await db.execute(
                    select(EmailAccount).where(EmailAccount.is_active == True)
                )
                accounts = result.scalars().all()

                logger.info(f"Found {len(accounts)} active email accounts to sync")

                for account in accounts:
                    try:
                        # Create services
                        event_repo = EventRepository(db)
                        schema_repo = EventSchemaRepository(db)
                        hash_service = HashService()
                        event_service = EventService(event_repo, schema_repo, hash_service)

                        # Sync account
                        sync_service = UniversalEmailSync(db, event_service)
                        stats = await sync_service.sync_account(account)

                        logger.info(
                            f"Synced {account.email_address}: "
                            f"{stats['events_created']} events created"
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to sync {account.email_address}: {e}",
                            exc_info=True
                        )
                        continue

                logger.info("Scheduled email sync completed")

            except Exception as e:
                logger.error(f"Scheduled sync failed: {e}", exc_info=True)


# Global scheduler instance
_email_scheduler = None


def get_email_scheduler() -> EmailSyncScheduler:
    """Get or create email scheduler"""
    global _email_scheduler
    if _email_scheduler is None:
        _email_scheduler = EmailSyncScheduler()
    return _email_scheduler
```

#### 3. Integrate with FastAPI Lifespan

```python
# main.py

from services.email_scheduler import get_email_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for database initialization"""
    # Initialize logging
    setup_logging()

    # Start email sync scheduler
    scheduler = get_email_scheduler()
    scheduler.start()

    yield

    # Shutdown
    scheduler.stop()
    await engine.dispose()
```

#### 4. Configuration

```python
# core/config.py

class Settings(BaseSettings):
    # ... existing settings

    # Email sync settings
    email_sync_enabled: bool = True
    email_sync_interval_minutes: int = 15  # Sync every 15 minutes
```

---

## Option 3: Celery Task Queue (Production Scale)

### Use Case
- Production deployment
- Distributed workers
- Retry logic
- Monitoring/dashboard

### Implementation

#### 1. Install Celery + Redis

```bash
pip install celery redis
```

#### 2. Create Celery App

```python
# tasks/celery_app.py

from celery import Celery
from core.config import get_settings

settings = get_settings()

celery_app = Celery(
    'timeline',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    worker_prefetch_multiplier=1,
)
```

#### 3. Create Email Sync Task

```python
# tasks/email_tasks.py

from tasks.celery_app import celery_app
from core.database import AsyncSessionLocal
from models.email_account import EmailAccount
from integrations.email.sync import UniversalEmailSync
from services.event_service import EventService
from repositories.event_repo import EventRepository
from repositories.event_schema_repo import EventSchemaRepository
from services.hash_service import HashService
from core.logging import get_logger
from sqlalchemy import select
import asyncio

logger = get_logger(__name__)


@celery_app.task(name='sync_email_account', bind=True, max_retries=3)
def sync_email_account_task(self, email_account_id: str, tenant_id: str):
    """
    Celery task to sync email account.

    Runs in background worker process.
    """
    try:
        # Run async code in sync context
        asyncio.run(_sync_email_account(email_account_id, tenant_id))
        return {"status": "success", "email_account_id": email_account_id}

    except Exception as e:
        logger.error(f"Email sync task failed: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


async def _sync_email_account(email_account_id: str, tenant_id: str):
    """Async function to sync email account"""
    async with AsyncSessionLocal() as db:
        # Get email account
        result = await db.execute(
            select(EmailAccount).where(
                EmailAccount.id == email_account_id,
                EmailAccount.tenant_id == tenant_id
            )
        )
        email_account = result.scalar_one_or_none()

        if not email_account:
            raise ValueError(f"Email account {email_account_id} not found")

        # Create services
        event_repo = EventRepository(db)
        schema_repo = EventSchemaRepository(db)
        hash_service = HashService()
        event_service = EventService(event_repo, schema_repo, hash_service)

        # Run sync
        sync_service = UniversalEmailSync(db, event_service)
        stats = await sync_service.sync_account(email_account)

        logger.info(f"Celery sync completed: {stats}")


@celery_app.task(name='sync_all_email_accounts')
def sync_all_accounts_task():
    """Sync all active email accounts"""
    asyncio.run(_sync_all_accounts())


async def _sync_all_accounts():
    """Sync all active email accounts"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EmailAccount).where(EmailAccount.is_active == True)
        )
        accounts = result.scalars().all()

        for account in accounts:
            # Queue individual sync tasks
            sync_email_account_task.delay(account.id, account.tenant_id)
```

#### 4. Update API Endpoint

```python
# api/email_accounts.py

from tasks.email_tasks import sync_email_account_task

@router.post("/{email_account_id}/sync-celery", status_code=status.HTTP_202_ACCEPTED)
async def sync_email_account_celery(
    email_account_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Queue email sync with Celery"""
    # Verify account exists
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == email_account_id,
            EmailAccount.tenant_id == tenant.id
        )
    )
    email_account = result.scalar_one_or_none()

    if not email_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found"
        )

    # Queue task
    task = sync_email_account_task.delay(email_account_id, tenant.id)

    return {
        "message": "Email sync queued",
        "task_id": task.id,
        "email_account_id": email_account_id
    }
```

#### 5. Setup Celery Beat for Scheduling

```python
# tasks/celery_app.py

from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'sync-emails-every-15-min': {
        'task': 'sync_all_email_accounts',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
}
```

#### 6. Run Celery Worker

```bash
# Terminal 1: Start worker
celery -A tasks.celery_app worker --loglevel=info

# Terminal 2: Start beat scheduler
celery -A tasks.celery_app beat --loglevel=info

# Terminal 3: Monitor (optional)
celery -A tasks.celery_app flower
```

---

## Comparison Matrix

| Feature | FastAPI BG | APScheduler | Celery |
|---------|------------|-------------|--------|
| **Setup Complexity** | Simple | Medium | Complex |
| **External Dependencies** | None | None | Redis/RabbitMQ |
| **Distributed Workers** | No | No | Yes |
| **Retry Logic** | Manual | Manual | Built-in |
| **Monitoring** | Basic | Basic | Advanced (Flower) |
| **Scalability** | Low | Medium | High |
| **Best For** | User-triggered | Scheduled | Production |

---

## Recommended Architecture

### Development/Small Scale
```
FastAPI Background Tasks + APScheduler
- User triggers: FastAPI BG
- Scheduled: APScheduler (15 min)
```

### Production/Large Scale
```
Celery + Redis + Celery Beat
- Distributed workers
- Retry logic
- Monitoring with Flower
- Horizontal scaling
```

---

## Monitoring & Status

### Track Sync Status (Database)

```python
# Add to email_account model
class EmailAccount(Base):
    # ... existing fields

    last_sync_status: str  # success, failed, in_progress
    last_sync_error: str  # Error message if failed
    sync_count: int  # Total syncs performed
```

### Status Endpoint

```python
@router.get("/{email_account_id}/sync-status")
async def get_sync_status(
    email_account_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    """Get sync status for email account"""
    result = await db.execute(
        select(EmailAccount).where(
            EmailAccount.id == email_account_id,
            EmailAccount.tenant_id == tenant.id
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="Not found")

    return {
        "email_address": account.email_address,
        "last_sync_at": account.last_sync_at,
        "last_sync_status": account.last_sync_status,
        "last_sync_error": account.last_sync_error,
        "sync_count": account.sync_count,
        "is_syncing": account.last_sync_status == "in_progress"
    }
```

---

## Next Steps

1. **Start Simple**: Implement FastAPI Background Tasks first
2. **Add Scheduling**: Add APScheduler for periodic sync
3. **Scale**: Move to Celery when you need:
   - Distributed workers
   - Advanced retry logic
   - Better monitoring
   - Horizontal scaling

Choose based on your current needs and scale up as required!
