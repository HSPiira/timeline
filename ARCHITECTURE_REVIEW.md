# Timeline Architecture Review
## FastAPI Best Practices & SOLID Design Principles

**Review Date**: December 13, 2024
**Current Implementation**: dev/timeline/
**Reference**: [FastAPI Learn Documentation](https://fastapi.tiangolo.com/learn/)

---

## Executive Summary

The current Timeline implementation has a **solid foundation** with clear separation of concerns (repositories, services, schemas, API routes). However, several opportunities exist to align with **FastAPI best practices** and **SOLID principles** for a production-ready, scalable, multi-tenant SaaS application.

**Overall Assessment**: 6/10 → Target: 9/10

**Key Strengths**:
✅ Layer separation (API, services, repositories, models, schemas)
✅ Hash service correctly implements cryptographic chaining
✅ Pydantic schemas for validation

**Critical Gaps**:
❌ Missing dependency injection (violates FastAPI patterns)
❌ No database session management
❌ Missing tenant context middleware
❌ No async/await (not leveraging FastAPI's async capabilities)
❌ Incomplete error handling
❌ Missing configuration management (Pydantic Settings)
❌ No interfaces/protocols (violates Dependency Inversion)
❌ Tight coupling between layers

---

## 1. Current Architecture Analysis

### 1.1 Project Structure

```
dev/timeline/
├── main.py                    # Entry point (minimal)
├── requirements.txt           # Dependencies (incomplete)
├── api/                       # Route handlers
│   ├── events.py
│   ├── tenant.py
│   ├── subject.py
│   ├── document.py
│   └── deps.py                # Dependencies (empty)
├── core/                      # Core infrastructure
│   ├── config.py              # Configuration (empty)
│   ├── database.py            # Database setup (sync only)
│   └── security.py            # Security (empty)
├── models/                    # SQLAlchemy models
│   ├── event.py
│   ├── tenant.py
│   ├── subject.py
│   └── document.py
├── schemas/                   # Pydantic schemas
│   ├── event.py
│   ├── tenant.py
│   ├── subject.py
│   └── document.py
├── services/                  # Business logic
│   ├── event_service.py
│   ├── hash_service.py
│   └── schema_registry.py
├── repositories/              # Data access
│   ├── base.py                # Base repository (empty)
│   ├── event_repo.py          # Event repository (empty)
│   ├── tenant_repo.py
│   └── subject_repo.py
└── utils/                     # Utilities
    └── generators.py
```

**Assessment**: Structure is good but many files are placeholders.

---

## 2. FastAPI Best Practices Alignment

### 2.1 Missing: Async/Await (CRITICAL)

**Current** (main.py, api/events.py):
```python
@router.post("/")
def create_event(event: EventCreate):  # ❌ Synchronous
    service = EventService(...)
    return service.create_event("tenant-id", event)
```

**FastAPI Recommendation**: Use async/await for I/O-bound operations (database, external APIs).

**Should Be**:
```python
@router.post("/")
async def create_event(
    event: EventCreate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant)
):  # ✅ Asynchronous
    service = EventService(db)
    return await service.create_event(tenant.id, event)
```

**Impact**: 3-5x better concurrency and throughput.

---

### 2.2 Missing: Dependency Injection (CRITICAL)

**Current Problem**:
```python
# api/events.py
@router.post("/")
def create_event(event: EventCreate):
    service = EventService(...)  # ❌ Manually instantiated
    return service.create_event("tenant-id", event)  # ❌ Hardcoded tenant
```

**Issues**:
1. ❌ No dependency injection
2. ❌ Hardcoded tenant ID
3. ❌ Service instantiation in route handler
4. ❌ No database session management

**FastAPI Pattern** (from docs):
```python
# api/deps.py
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

async def get_db() -> AsyncSession:
    """Database session dependency"""
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_tenant(
    x_tenant_id: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """Resolve tenant from header"""
    tenant = await TenantRepository(db).get_by_id(x_tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

async def get_event_service(
    db: AsyncSession = Depends(get_db)
) -> EventService:
    """Event service dependency"""
    return EventService(
        event_repo=EventRepository(db),
        hash_service=HashService()
    )
```

**Correct Route**:
```python
# api/events.py
@router.post("/", response_model=EventResponse)
async def create_event(
    event: EventCreate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    service: Annotated[EventService, Depends(get_event_service)]
):
    return await service.create_event(tenant.id, event)
```

**Benefits**:
✅ Automatic session management
✅ Testable (can inject mocks)
✅ Clear dependencies
✅ Follows FastAPI patterns

---

### 2.3 Missing: Pydantic Settings (Configuration)

**Current** (core/config.py):
```python
# ❌ Empty file
```

**FastAPI Recommendation** (from docs):
```python
# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    """Application configuration"""

    # App
    app_name: str = "Timeline"
    app_version: str = "1.0.0"
    debug: bool = False

    # Database
    database_url: str
    database_echo: bool = False

    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Storage
    s3_bucket: str
    s3_region: str = "us-east-1"

    # Tenant
    tenant_header_name: str = "X-Tenant-ID"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    return Settings()
```

**Usage**:
```python
from core.config import get_settings

settings = get_settings()  # Reads from .env, cached
DATABASE_URL = settings.database_url
```

---

### 2.4 Missing: Proper Database Session Management

**Current** (core/database.py):
```python
# ❌ Synchronous only, no async support
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
```

**FastAPI Recommendation** (async):
```python
# core/database.py
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy.orm import declarative_base
from core.config import get_settings

settings = get_settings()

# Async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,  # Health checks
    pool_size=10,
    max_overflow=20
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

Base = declarative_base()

# Dependency for routes
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

---

### 2.5 Missing: Response Models

**Current**:
```python
@router.post("/")
def create_event(event: EventCreate):
    return service.create_event("tenant-id", event)  # ❌ No response model
```

**FastAPI Best Practice**:
```python
# schemas/event.py
class EventResponse(BaseModel):
    id: str
    tenant_id: str
    subject_id: str
    event_type: str
    event_time: datetime
    payload: Dict[str, Any]
    hash: str
    previous_hash: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# api/events.py
@router.post("/", response_model=EventResponse, status_code=201)
async def create_event(
    event: EventCreate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    service: Annotated[EventService, Depends(get_event_service)]
):
    return await service.create_event(tenant.id, event)
```

**Benefits**:
✅ Automatic response validation
✅ OpenAPI documentation
✅ Type safety

---

### 2.6 Missing: Proper Error Handling

**Current**: No custom exception handling.

**FastAPI Pattern**:
```python
# core/exceptions.py
from fastapi import HTTPException, status

class TimelineException(Exception):
    """Base exception"""
    pass

class TenantNotFoundException(TimelineException):
    """Tenant not found"""
    pass

class EventChainBrokenException(TimelineException):
    """Event chain integrity violated"""
    pass

class SchemaValidationException(TimelineException):
    """Schema validation failed"""
    pass

# main.py
from fastapi import Request, status
from fastapi.responses import JSONResponse

@app.exception_handler(TenantNotFoundException)
async def tenant_not_found_handler(request: Request, exc: TenantNotFoundException):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Tenant not found"}
    )

@app.exception_handler(EventChainBrokenException)
async def chain_broken_handler(request: Request, exc: EventChainBrokenException):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Event chain integrity compromised"}
    )
```

---

### 2.7 Missing: Lifespan Events

**Current** (main.py):
```python
app = FastAPI(title="Timeline", version="1.0.0")
# ❌ No startup/shutdown logic
```

**FastAPI Pattern**:
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Timeline...")

    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize Redis cache
    redis_client = await aioredis.from_url(settings.redis_url)
    app.state.redis = redis_client

    yield  # Application runs

    # Shutdown
    print("🛑 Shutting down Timeline...")
    await redis_client.close()
    await engine.dispose()

app = FastAPI(
    title="Timeline",
    version="1.0.0",
    lifespan=lifespan
)
```

---

### 2.8 Missing: API Versioning & Tenant Scoping

**Current**:
```python
app.include_router(events.router, prefix="/events")  # ❌ No versioning, no tenant scope
```

**Recommended** (per timeline.md):
```python
# main.py
from api import events, subjects, documents, tenants

# API v1
api_v1 = APIRouter(prefix="/api/v1")

# Tenant-scoped routes
tenant_router = APIRouter(prefix="/tenants/{tenant_id}")
tenant_router.include_router(events.router, prefix="/events", tags=["Events"])
tenant_router.include_router(subjects.router, prefix="/subjects", tags=["Subjects"])
tenant_router.include_router(documents.router, prefix="/documents", tags=["Documents"])

# Admin routes (not tenant-scoped)
api_v1.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])

# Global routes
api_v1.include_router(tenant_router)

app.include_router(api_v1)
```

**URL Structure**:
```
POST /api/v1/tenants/{tenant_id}/events
GET  /api/v1/tenants/{tenant_id}/subjects/{subject_id}/timeline
POST /api/v1/tenants/{tenant_id}/documents
```

---

## 3. SOLID Principles Evaluation

### 3.1 Single Responsibility Principle (SRP)

**Current Issues**:

❌ **EventService** does too much:
```python
class EventService:
    def create_event(self, tenant_id, data):
        prev = self.repo.get_last_hash(data.subject_id)  # ❌ Data access
        event_hash = HashService.compute(...)             # ✅ OK
        return self.repo.create(...)                      # ❌ Data access
```

**Problem**: Service mixes business logic with data access decisions.

**Better Approach** (SRP):
```python
# services/event_service.py
class EventService:
    """Business logic ONLY"""

    def __init__(
        self,
        event_repo: IEventRepository,  # Interface, not concrete class
        hash_service: IHashService,
        validator: IEventValidator
    ):
        self._event_repo = event_repo
        self._hash_service = hash_service
        self._validator = validator

    async def create_event(
        self,
        tenant_id: str,
        event_data: EventCreate
    ) -> Event:
        # 1. Validate (delegated)
        await self._validator.validate(tenant_id, event_data)

        # 2. Get previous hash (delegated)
        previous_hash = await self._event_repo.get_last_hash(
            tenant_id,
            event_data.subject_id
        )

        # 3. Compute hash (delegated)
        event_hash = self._hash_service.compute_hash(
            tenant_id=tenant_id,
            subject_id=event_data.subject_id,
            event_type=event_data.event_type,
            event_time=event_data.event_time,
            payload=event_data.payload,
            previous_hash=previous_hash
        )

        # 4. Create event (delegated)
        event = await self._event_repo.create(
            tenant_id=tenant_id,
            event_data=event_data,
            event_hash=event_hash,
            previous_hash=previous_hash
        )

        # 5. Execute workflows (delegated)
        # This could be async (fire and forget)

        return event
```

**Each class has ONE reason to change**.

---

### 3.2 Open/Closed Principle (OCP)

**Current Issue**: No extensibility for new event types or validators.

**Better Approach**:
```python
# services/validators/base.py
from abc import ABC, abstractmethod

class IEventValidator(ABC):
    """Event validator interface"""

    @abstractmethod
    async def validate(
        self,
        tenant_id: str,
        event_data: EventCreate
    ) -> None:
        """Validate event, raise ValidationError if invalid"""
        pass

# services/validators/schema_validator.py
class SchemaValidator(IEventValidator):
    """Validates event payload against schema registry"""

    def __init__(self, schema_registry: ISchemaRegistry):
        self._schema_registry = schema_registry

    async def validate(self, tenant_id: str, event_data: EventCreate):
        schema = await self._schema_registry.get_active_schema(
            tenant_id,
            event_data.event_type
        )

        if not schema:
            raise SchemaNotFoundException(
                f"No schema for {event_data.event_type}"
            )

        # Validate payload against JSON schema
        try:
            jsonschema.validate(
                instance=event_data.payload,
                schema=schema.schema_json
            )
        except jsonschema.ValidationError as e:
            raise SchemaValidationException(str(e))

# services/validators/composite_validator.py
class CompositeEventValidator(IEventValidator):
    """Run multiple validators"""

    def __init__(self, validators: list[IEventValidator]):
        self._validators = validators

    async def validate(self, tenant_id: str, event_data: EventCreate):
        for validator in self._validators:
            await validator.validate(tenant_id, event_data)
```

**Usage**:
```python
# api/deps.py
async def get_event_validator() -> IEventValidator:
    return CompositeEventValidator([
        SchemaValidator(schema_registry),
        SubjectExistsValidator(subject_repo),
        TenantActiveValidator(tenant_repo)
    ])
```

**Benefits**:
✅ Add new validators without modifying EventService
✅ Compose validators flexibly
✅ Testable in isolation

---

### 3.3 Liskov Substitution Principle (LSP)

**Current Issue**: No interfaces, so substitution is impossible.

**Better Approach** (use Protocols):
```python
# repositories/interfaces.py
from typing import Protocol, Optional
from models.event import Event
from schemas.event import EventCreate

class IEventRepository(Protocol):
    """Event repository interface"""

    async def create(
        self,
        tenant_id: str,
        event_data: EventCreate,
        event_hash: str,
        previous_hash: Optional[str]
    ) -> Event:
        """Create a new event"""
        ...

    async def get_by_id(
        self,
        tenant_id: str,
        event_id: str
    ) -> Optional[Event]:
        """Get event by ID"""
        ...

    async def get_last_hash(
        self,
        tenant_id: str,
        subject_id: str
    ) -> Optional[str]:
        """Get hash of last event for subject"""
        ...

    async def get_timeline(
        self,
        tenant_id: str,
        subject_id: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> list[Event]:
        """Get timeline for subject"""
        ...

# repositories/event_repository.py
class PostgresEventRepository:
    """PostgreSQL implementation of IEventRepository"""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(
        self,
        tenant_id: str,
        event_data: EventCreate,
        event_hash: str,
        previous_hash: Optional[str]
    ) -> Event:
        event = Event(
            tenant_id=tenant_id,
            subject_id=event_data.subject_id,
            event_type=event_data.event_type,
            event_time=event_data.event_time,
            payload=event_data.payload,
            hash=event_hash,
            previous_hash=previous_hash
        )

        self._db.add(event)
        await self._db.flush()
        await self._db.refresh(event)

        return event

    # ... other methods
```

**Benefits**:
✅ Can swap PostgreSQL for MongoDB without changing services
✅ Easy to mock for testing
✅ Clear contracts

---

### 3.4 Interface Segregation Principle (ISP)

**Current**: N/A (no interfaces yet)

**Recommendation**:
```python
# Don't create fat interfaces
# ❌ BAD
class IEventRepository(Protocol):
    async def create(...): ...
    async def update(...): ...  # Events are immutable!
    async def delete(...): ...  # Events can't be deleted!
    async def get_timeline(...): ...
    async def search(...): ...
    async def export(...): ...
    # ... 20 more methods

# ✅ GOOD - Split into focused interfaces
class IEventWriter(Protocol):
    async def create(...): ...

class IEventReader(Protocol):
    async def get_by_id(...): ...
    async def get_timeline(...): ...

class IEventSearcher(Protocol):
    async def search(...): ...
    async def search_by_type(...): ...

# Services depend only on what they need
class EventService:
    def __init__(
        self,
        writer: IEventWriter,
        reader: IEventReader,
        hasher: IHashService
    ):
        # Only needs writer and reader, not searcher
        ...
```

---

### 3.5 Dependency Inversion Principle (DIP)

**Current Problem**:
```python
# services/event_service.py
from repositories.event_repo import EventRepository  # ❌ Depends on concrete class

class EventService:
    def __init__(self, repo: EventRepository):  # ❌ Tightly coupled
        self.repo = repo
```

**Better Approach** (DIP):
```python
# services/event_service.py
from repositories.interfaces import IEventRepository  # ✅ Depends on interface

class EventService:
    def __init__(self, repo: IEventRepository):  # ✅ Depends on abstraction
        self._repo = repo
```

**Dependency Graph**:
```
Before (❌ Violation):
EventService → PostgresEventRepository → SQLAlchemy

After (✅ DIP):
EventService → IEventRepository ← PostgresEventRepository
                     ↑
                Interface
```

**Benefits**:
✅ EventService doesn't know about PostgreSQL
✅ Can inject mocks for testing
✅ Can swap database without changing service

---

## 4. Missing Requirements (From timeline.md)

### 4.1 Row-Level Security (RLS)

**Required**: PostgreSQL RLS for tenant isolation.

**Implementation**:
```sql
-- migrations/001_enable_rls.sql

-- Enable RLS on all tables
ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE subject ENABLE ROW LEVEL SECURITY;
ALTER TABLE event ENABLE ROW LEVEL SECURITY;
ALTER TABLE document ENABLE ROW LEVEL SECURITY;

-- Tenant isolation policy
CREATE POLICY tenant_isolation_subjects ON subject
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE POLICY tenant_isolation_events ON event
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Prevent updates on events (immutability)
CREATE POLICY events_immutable ON event
    FOR UPDATE USING (false);

CREATE POLICY events_no_delete ON event
    FOR DELETE USING (false);
```

**Application-Level**:
```python
# repositories/base.py
class BaseRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def set_tenant_context(self, tenant_id: str):
        """Set PostgreSQL session variable for RLS"""
        await self._db.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, false)"),
            {"tenant_id": tenant_id}
        )
```

---

### 4.2 Chain Verification API

**Required**: Endpoint to verify event chain integrity.

**Implementation**:
```python
# api/events.py
@router.get("/subjects/{subject_id}/verify-chain")
async def verify_event_chain(
    subject_id: str,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    service: Annotated[EventService, Depends(get_event_service)]
):
    """Verify cryptographic event chain for a subject"""

    result = await service.verify_chain(tenant.id, subject_id)

    return {
        "subject_id": subject_id,
        "chain_valid": result.is_valid,
        "total_events": result.total_events,
        "first_event_id": result.first_event_id,
        "last_event_id": result.last_event_id,
        "last_hash": result.last_hash,
        "verified_at": datetime.utcnow(),
        "broken_at_sequence": result.broken_at_sequence if not result.is_valid else None
    }
```

---

### 4.3 Schema Registry

**Required**: Tenant-owned schema management.

**Implementation**:
```python
# api/schemas.py (new file)
from fastapi import APIRouter, Depends
from typing import Annotated

router = APIRouter()

@router.post("/event-types", response_model=EventTypeResponse)
async def create_event_type(
    event_type: EventTypeCreate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    service: Annotated[SchemaRegistryService, Depends(get_schema_service)]
):
    """Register a new event type for tenant"""
    return await service.create_event_type(tenant.id, event_type)

@router.get("/event-types", response_model=list[EventTypeResponse])
async def list_event_types(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    service: Annotated[SchemaRegistryService, Depends(get_schema_service)]
):
    """List all event types configured for tenant"""
    return await service.list_event_types(tenant.id)
```

---

## 5. Recommended Project Structure (FastAPI Best Practices)

```
timeline/
├── alembic/                       # Database migrations
│   ├── versions/
│   └── env.py
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app instance
│   │
│   ├── api/                       # API routes
│   │   ├── __init__.py
│   │   ├── deps.py                # Dependencies (get_db, get_current_tenant, etc.)
│   │   └── v1/                    # API version 1
│   │       ├── __init__.py
│   │       ├── events.py
│   │       ├── subjects.py
│   │       ├── documents.py
│   │       ├── tenants.py
│   │       └── schemas.py
│   │
│   ├── core/                      # Core infrastructure
│   │   ├── __init__.py
│   │   ├── config.py              # Pydantic Settings
│   │   ├── database.py            # Async SQLAlchemy
│   │   ├── security.py            # JWT, hashing, etc.
│   │   └── exceptions.py          # Custom exceptions
│   │
│   ├── models/                    # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── base.py                # Base model class
│   │   ├── tenant.py
│   │   ├── subject.py
│   │   ├── event.py
│   │   ├── document.py
│   │   └── schema_registry.py
│   │
│   ├── schemas/                   # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── tenant.py
│   │   ├── subject.py
│   │   ├── event.py
│   │   ├── document.py
│   │   └── common.py              # Shared schemas
│   │
│   ├── repositories/              # Data access layer
│   │   ├── __init__.py
│   │   ├── interfaces.py          # Protocols/interfaces
│   │   ├── base.py                # Base repository
│   │   ├── tenant_repository.py
│   │   ├── subject_repository.py
│   │   ├── event_repository.py
│   │   └── document_repository.py
│   │
│   ├── services/                  # Business logic
│   │   ├── __init__.py
│   │   ├── tenant_service.py
│   │   ├── subject_service.py
│   │   ├── event_service.py
│   │   ├── document_service.py
│   │   ├── hash_service.py
│   │   ├── schema_registry_service.py
│   │   └── validators/            # Validators
│   │       ├── __init__.py
│   │       ├── interfaces.py
│   │       ├── schema_validator.py
│   │       └── composite_validator.py
│   │
│   └── utils/                     # Utilities
│       ├── __init__.py
│       ├── generators.py
│       └── crypto.py
│
├── tests/                         # Tests
│   ├── __init__.py
│   ├── conftest.py                # Pytest fixtures
│   ├── unit/
│   │   ├── test_hash_service.py
│   │   └── test_event_service.py
│   ├── integration/
│   │   └── test_event_creation.py
│   └── e2e/
│       └── test_timeline_flow.py
│
├── migrations/                    # SQL migrations (manual)
│   ├── 001_create_core_tables.sql
│   ├── 002_enable_rls.sql
│   └── 003_create_indexes.sql
│
├── .env.example                   # Environment variables template
├── .gitignore
├── alembic.ini                    # Alembic config
├── docker-compose.yml             # Local development
├── Dockerfile
├── pyproject.toml                 # Poetry/pip config
├── README.md
└── requirements.txt
```

---

## 6. Priority Action Items

### Phase 1: Foundation (Week 1)

1. **Add AsyncIO Support** (CRITICAL)
   - Migrate to `sqlalchemy.ext.asyncio`
   - Add `async`/`await` to all database operations
   - Update route handlers to be async

2. **Implement Dependency Injection** (CRITICAL)
   - Create `api/deps.py` with proper dependencies
   - Add `get_db()`, `get_current_tenant()`, `get_*_service()` functions
   - Use `Depends()` in all route handlers

3. **Add Pydantic Settings** (HIGH)
   - Create `core/config.py` with `BaseSettings`
   - Move all configuration to environment variables
   - Add `.env.example`

4. **Implement Response Models** (HIGH)
   - Create response schemas for all endpoints
   - Add `response_model` to route decorators
   - Enable automatic documentation

### Phase 2: SOLID Refactoring (Week 2)

5. **Create Interfaces** (HIGH)
   - Define `Protocol` classes for repositories
   - Define `Protocol` classes for services
   - Update services to depend on abstractions

6. **Implement Validators** (HIGH)
   - Create `IEventValidator` interface
   - Implement `SchemaValidator`, `SubjectExistsValidator`
   - Use composite pattern for multiple validators

7. **Add Error Handling** (HIGH)
   - Create custom exception classes
   - Add exception handlers to `main.py`
   - Return proper HTTP status codes

### Phase 3: Multi-Tenancy (Week 3)

8. **Implement RLS** (CRITICAL)
   - Write SQL migration for RLS policies
   - Add `set_tenant_context()` to repositories
   - Test tenant isolation

9. **Add Tenant Middleware** (CRITICAL)
   - Create middleware to extract tenant from header/subdomain
   - Set tenant context on every request
   - Add tenant validation

10. **Implement Chain Verification** (MEDIUM)
    - Add verification endpoint
    - Add periodic background job
    - Log integrity violations

### Phase 4: Testing & Documentation (Week 4)

11. **Add Tests** (HIGH)
    - Unit tests for services (with mocks)
    - Integration tests for repositories
    - E2E tests for API endpoints

12. **Improve Documentation** (MEDIUM)
    - Add docstrings to all functions
    - Configure OpenAPI metadata
    - Add examples to endpoints

---

## 7. Code Quality Checklist

Before merging any PR:

### FastAPI Best Practices
- [ ] All route handlers are `async`
- [ ] All dependencies use `Depends()`
- [ ] All routes have `response_model`
- [ ] All routes have proper HTTP status codes
- [ ] Configuration uses `Pydantic Settings`
- [ ] Database uses async SQLAlchemy
- [ ] Lifespan events handle startup/shutdown

### SOLID Principles
- [ ] Each class has single responsibility (SRP)
- [ ] New functionality added via extension, not modification (OCP)
- [ ] Services depend on interfaces, not concrete classes (DIP)
- [ ] Interfaces are small and focused (ISP)
- [ ] Implementations are interchangeable (LSP)

### Multi-Tenancy
- [ ] All queries filtered by tenant_id
- [ ] RLS policies enforced
- [ ] Tenant context set on every request
- [ ] No cross-tenant data leakage

### Event Sourcing
- [ ] Events are immutable (no UPDATE/DELETE)
- [ ] Hash chaining is correct
- [ ] Chain verification passes
- [ ] Payload validated against schema

### Testing
- [ ] Unit tests for services (80%+ coverage)
- [ ] Integration tests for repositories
- [ ] E2E tests for critical flows
- [ ] Tests use mocks/fixtures properly

---

## 8. Example: Refactored Event Creation (End-to-End)

### 8.1 Configuration

```python
# core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    tenant_header_name: str = "X-Tenant-ID"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### 8.2 Database

```python
# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### 8.3 Models

```python
# models/event.py
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, text
from sqlalchemy.dialects.postgresql import UUID
from core.database import Base
import datetime

class Event(Base):
    __tablename__ = "event"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subject.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    event_time = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=False)
    hash = Column(String(64), nullable=False)
    previous_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
```

### 8.4 Schemas

```python
# schemas/event.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

class EventCreate(BaseModel):
    subject_id: UUID
    event_type: str
    event_time: datetime
    payload: Dict[str, Any]

class EventResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    subject_id: UUID
    event_type: str
    event_time: datetime
    payload: Dict[str, Any]
    hash: str
    previous_hash: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

### 8.5 Repository Interface

```python
# repositories/interfaces.py
from typing import Protocol, Optional
from uuid import UUID
from models.event import Event
from schemas.event import EventCreate

class IEventRepository(Protocol):
    async def create(
        self,
        tenant_id: UUID,
        event_data: EventCreate,
        event_hash: str,
        previous_hash: Optional[str]
    ) -> Event: ...

    async def get_last_hash(
        self,
        tenant_id: UUID,
        subject_id: UUID
    ) -> Optional[str]: ...
```

### 8.6 Repository Implementation

```python
# repositories/event_repository.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text
from models.event import Event
from schemas.event import EventCreate
from typing import Optional
from uuid import UUID

class PostgresEventRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def set_tenant_context(self, tenant_id: UUID):
        await self._db.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, false)"),
            {"tenant_id": str(tenant_id)}
        )

    async def create(
        self,
        tenant_id: UUID,
        event_data: EventCreate,
        event_hash: str,
        previous_hash: Optional[str]
    ) -> Event:
        await self.set_tenant_context(tenant_id)

        event = Event(
            tenant_id=tenant_id,
            subject_id=event_data.subject_id,
            event_type=event_data.event_type,
            event_time=event_data.event_time,
            payload=event_data.payload,
            hash=event_hash,
            previous_hash=previous_hash
        )

        self._db.add(event)
        await self._db.flush()
        await self._db.refresh(event)

        return event

    async def get_last_hash(
        self,
        tenant_id: UUID,
        subject_id: UUID
    ) -> Optional[str]:
        await self.set_tenant_context(tenant_id)

        stmt = (
            select(Event.hash)
            .where(Event.subject_id == subject_id)
            .order_by(desc(Event.created_at))
            .limit(1)
        )

        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
```

### 8.7 Service

```python
# services/event_service.py
from repositories.interfaces import IEventRepository
from services.hash_service import HashService
from schemas.event import EventCreate
from models.event import Event
from uuid import UUID

class EventService:
    def __init__(
        self,
        event_repo: IEventRepository,
        hash_service: HashService
    ):
        self._event_repo = event_repo
        self._hash_service = hash_service

    async def create_event(
        self,
        tenant_id: UUID,
        event_data: EventCreate
    ) -> Event:
        # Get previous hash
        previous_hash = await self._event_repo.get_last_hash(
            tenant_id,
            event_data.subject_id
        )

        # Compute hash
        event_hash = self._hash_service.compute_hash(
            tenant_id=str(tenant_id),
            subject_id=str(event_data.subject_id),
            event_type=event_data.event_type,
            event_time=event_data.event_time,
            payload=event_data.payload,
            previous_hash=previous_hash or "GENESIS"
        )

        # Create event
        event = await self._event_repo.create(
            tenant_id=tenant_id,
            event_data=event_data,
            event_hash=event_hash,
            previous_hash=previous_hash
        )

        return event
```

### 8.8 Dependencies

```python
# api/deps.py
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from uuid import UUID

from core.database import get_db
from repositories.tenant_repository import PostgresTenantRepository
from repositories.event_repository import PostgresEventRepository
from services.event_service import EventService
from services.hash_service import HashService
from models.tenant import Tenant

async def get_current_tenant(
    x_tenant_id: Annotated[UUID, Header()],
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    tenant_repo = PostgresTenantRepository(db)
    tenant = await tenant_repo.get_by_id(x_tenant_id)

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if tenant.status != "active":
        raise HTTPException(status_code=403, detail="Tenant is not active")

    return tenant

async def get_event_service(
    db: AsyncSession = Depends(get_db)
) -> EventService:
    return EventService(
        event_repo=PostgresEventRepository(db),
        hash_service=HashService()
    )
```

### 8.9 API Route

```python
# api/v1/events.py
from fastapi import APIRouter, Depends, status
from typing import Annotated

from schemas.event import EventCreate, EventResponse
from services.event_service import EventService
from models.tenant import Tenant
from api.deps import get_current_tenant, get_event_service

router = APIRouter()

@router.post(
    "/",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new event",
    description="Creates an immutable event with cryptographic chaining"
)
async def create_event(
    event: EventCreate,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    service: Annotated[EventService, Depends(get_event_service)]
):
    """
    Create a new event for a subject.

    - **subject_id**: UUID of the subject
    - **event_type**: Type of event (must be registered in schema registry)
    - **event_time**: When the event occurred
    - **payload**: Event-specific data (validated against schema)
    """
    return await service.create_event(tenant.id, event)
```

### 8.10 Main App

```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.config import get_settings
from core.database import engine, Base
from api.v1 import events, subjects, documents

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Shutdown
    await engine.dispose()

app = FastAPI(
    title="Timeline",
    version="1.0.0",
    description="Multi-tenant enterprise event timeline system",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(
    events.router,
    prefix="/api/v1/tenants/{tenant_id}/events",
    tags=["Events"]
)
app.include_router(
    subjects.router,
    prefix="/api/v1/tenants/{tenant_id}/subjects",
    tags=["Subjects"]
)
```

---

## 9. Summary & Next Steps

### Current State Assessment

**Strengths**:
- ✅ Good layer separation
- ✅ Correct hash implementation
- ✅ Basic Pydantic usage

**Critical Gaps**:
- ❌ No async/await (poor performance)
- ❌ No dependency injection (violates FastAPI patterns)
- ❌ No interfaces (violates SOLID)
- ❌ Missing tenant isolation (security risk)
- ❌ Incomplete configuration management
- ❌ No error handling

### Recommended Approach

**Week 1**: Add async/await + dependency injection
**Week 2**: SOLID refactoring (interfaces, validators)
**Week 3**: Multi-tenancy (RLS, middleware)
**Week 4**: Testing + documentation

### Expected Outcomes

**Performance**: 3-5x better throughput with async
**Maintainability**: 10x easier to test and extend with SOLID
**Security**: Multi-tenant isolation enforced at DB level
**Quality**: Production-ready with tests and documentation

---

**This architecture review provides a roadmap to transform the current codebase into a production-ready, scalable, multi-tenant SaaS application following FastAPI best practices and SOLID principles.**
