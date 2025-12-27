# Timeline

Timeline is a multi-tenant event sourcing system built with FastAPI. It provides cryptographically-secure event chains, domain-driven design, and complete tenant isolation for building audit trails and temporal data systems.

Requires Python 3.9+ and PostgreSQL 12+.

## Getting started

Register a user account and start tracking events:

```python
import httpx

# Create a tenant first
tenant = httpx.post("http://localhost:8000/tenants/", json={
    "code": "acme-corp",  # lowercase, 3-15 chars, alphanumeric with optional hyphens
    "name": "ACME Corporation",
    "status": "active"
}).json()

# Register a new user account
user = httpx.post("http://localhost:8000/users/register", json={
    "tenant_code": "acme-corp",  # must match existing tenant code
    "username": "alice",
    "email": "alice@example.com",
    "password": "securepass123"  # min 8 characters
}).json()

# Authenticate and get access token
response = httpx.post("http://localhost:8000/auth/token", json={
    "username": "alice",
    "password": "securepass123",
    "tenant_code": "acme-corp"
})
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Create a subject to track
subject = httpx.post(
    "http://localhost:8000/subjects",
    headers=headers,
    json={"subject_type": "user", "external_ref": "user_123"}
).json()

# Record an event
event = httpx.post(
    "http://localhost:8000/events",
    headers=headers,
    json={
        "subject_id": subject["id"],
        "event_type": "created",
        "event_time": "2025-01-15T10:30:00Z",
        "payload": {"email": "user@example.com"}
    }
).json()
```

Events are automatically chained with SHA-256 hashes, creating an immutable audit trail.

## Features

### Multi-tenant isolation

Complete tenant separation at the database, authentication, and API layers. JWT tokens contain tenant claims, preventing cross-tenant data access:

```python
# Token contains tenant_id claim
{
    "sub": "user_id",
    "tenant_id": "tenant_abc",  # Enforced on every request
    "exp": 1234567890
}
```

All database queries include tenant filters. Attempting to access another tenant's data returns `403 Forbidden`.

### Event sourcing with cryptographic chaining

Events form an immutable chain secured by SHA-256 hashes. Each event references its predecessor:

```python
# First event (genesis)
event_1 = {
    "hash": "abc123...",
    "previous_hash": None,
    "payload": {"status": "created"}
}

# Subsequent event
event_2 = {
    "hash": "def456...",
    "previous_hash": "abc123...",  # Links to event_1
    "payload": {"status": "updated"}
}
```

Breaking the chain is cryptographically detectable, ensuring audit trail integrity.

### Document management

Attach documents to subjects and events with version control and soft deletion:

```python
document = httpx.post(
    "http://localhost:8000/documents",
    headers=headers,
    json={
        "subject_id": subject_id,
        "event_id": event_id,  # Optional
        "document_type": "invoice",
        "filename": "2025-01-invoice.pdf",
        "storage_ref": "s3://bucket/path/to/file",
        "checksum": "sha256...",
        # ... metadata
    }
).json()
```

Duplicate detection via checksum prevents redundant storage.

### Domain-driven design

Clean separation of concerns with value objects, entities, and repositories:

```python
from domain.value_objects import EventType, Hash, EventChain
from domain.entities import EventEntity

# Value objects enforce invariants at construction
event_type = EventType("status_changed")  # Validates format
hash_value = Hash("a" * 64)  # Validates SHA-256 format

# Entities contain business logic
chain = EventChain(current_hash=hash_value, previous_hash=None)
assert chain.is_genesis_event()  # True for first event
```

Value objects are immutable and self-validating. Invalid states cannot be constructed.

## Installation

Timeline uses Alembic for database migrations:

```console
$ pip install -r requirements.txt
$ alembic upgrade head  # Run migrations
$ uvicorn main:app --reload
```

Configure via `.env` file:

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/timeline_db
SECRET_KEY=your-secret-key-here
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080
S3_BUCKET=your-documents-bucket
```

## Database migrations

Create new migrations after model changes:

```console
$ alembic revision --autogenerate -m "Add new field"
$ alembic upgrade head
```

Rollback migrations:

```console
$ alembic downgrade -1  # One version back
$ alembic downgrade base  # Remove all
```

Alembic tracks schema versions and handles concurrent changes safely.

## Architecture

Timeline implements SOLID principles with clean architecture:

- **Domain layer**: Value objects and entities with business logic
- **Repository layer**: Data access with SQLAlchemy models
- **Service layer**: Application logic and orchestration
- **API layer**: FastAPI endpoints with dependency injection

```
api/          # FastAPI routes
├── auth.py   # JWT authentication
├── events.py # Event endpoints
└── ...

domain/              # Business logic
├── entities.py      # Domain entities
└── value_objects.py # Immutable value types

repositories/   # Data access
├── base.py     # Generic repository
├── event_repo.py
└── ...

services/          # Application logic
├── event_service.py
└── hash_service.py
```

### Security

**User registration and authentication**:
- Users register with tenant code, username, email, and password
- Passwords hashed with bcrypt (salt + hash)
- Username and email unique within tenant
- JWT tokens contain user_id and tenant_id claims

**Tenant code requirements**:
- 3-15 characters
- Lowercase alphanumeric with optional hyphens
- Abbreviation-based (e.g., `acme`, `acme-corp`, `abc123`)
- Immutable once tenant is activated

**JWT-based authentication**: All endpoints require Bearer tokens with embedded tenant claims.

**Tenant isolation enforcement**:
- Token validation extracts tenant_id from JWT
- Database queries automatically filter by tenant
- Cross-tenant references validated and rejected
- Attempting to access another tenant's data returns `403 Forbidden`

**Race-free uniqueness**: Database constraints prevent duplicate tenant codes and emails atomically.

**Cryptographic integrity**: SHA-256 event chains detect tampering.

**Password security**: Bcrypt hashing with automatic salt generation.

## Testing

Run tests with pytest:

```console
$ pytest tests/
$ pytest --cov=. --cov-report=html  # With coverage
```

Tests cover:
- Authentication and authorization
- Tenant isolation
- Event chain integrity
- Repository operations
- API endpoint behavior

## API documentation

Interactive API docs available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project structure

Timeline follows domain-driven design with clear layer separation:

**Core**: Configuration, database, enums, exceptions
**Domain**: Business entities and value objects
**Repositories**: Data persistence layer
**Services**: Application logic
**API**: HTTP endpoints
**Schemas**: Request/response validation

All layers follow the Dependency Inversion Principle. The domain layer has no dependencies on infrastructure.

## Performance

Timeline uses async SQLAlchemy with asyncpg for high-throughput PostgreSQL access. Connection pooling is configured via `DATABASE_URL` parameters:

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host/db?pool_size=20&max_overflow=10
```

For read-heavy workloads, use read replicas with separate database sessions. Event queries are optimized with compound indexes on `(tenant_id, subject_id, event_time)`.

## Related projects

- [FastAPI](https://fastapi.tiangolo.com/) - Modern async web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - SQL toolkit with async support
- [Alembic](https://alembic.sqlalchemy.org/) - Database migration tool
- [Pydantic](https://docs.pydantic.dev/) - Data validation with Python type hints

## License

See LICENSE file for details.

## Contributing

Contributions welcome! Please ensure:
- All tests pass (`pytest`)
- Code follows type hints and formatting (`mypy`, `black`)
- Security vulnerabilities are reported privately
- Migrations are tested with upgrade/downgrade cycles
