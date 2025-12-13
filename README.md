# Timeline

**Multi-Tenant Enterprise Memory System**

Timeline is an event-sourced system of record that captures organizational history immutably and cryptographically. Think "Git for business events" or "enterprise blockchain" - every action is recorded as an immutable, verifiable event with cryptographic proof.

---

## What Timeline Is

**Timeline is NOT a traditional document management system.**

Instead, Timeline is:

- **Event-Sourcing System (75%)** - Immutable audit trail of business facts
- **Evidence Management (25%)** - Documents attached as proof of events

### Core Philosophy

From the specification:
> Everything that happens is recorded as an **event**
> Events are immutable and append-only
> Documents are **evidence attached to events**
> "Current state" is **derived**, never stored as truth

**The Key Inversion**: Documents don't drive the system - events do. Documents are proof that events occurred.

---

## Why Timeline Exists

### Problems with Traditional Systems

❌ **Mutable History** - Records can be changed/deleted silently
❌ **No Cryptographic Proof** - Can't verify integrity
❌ **Document-Centric** - Files are primary, context is secondary
❌ **Siloed Truth** - Each system has its own version of reality
❌ **Weak Audit Trails** - Logs can be tampered with

### Timeline's Solution

✅ **Immutable Events** - History cannot be rewritten
✅ **Cryptographic Chaining** - Blockchain-style tamper-proof hashing
✅ **Event-Centric** - Business facts first, documents as evidence
✅ **Single Source of Truth** - Unified timeline across all systems
✅ **Cryptographically Verifiable** - Mathematical proof of what happened

---

## Core Concepts

### 1. Tenant
An organization using Timeline. Complete data isolation.

### 2. Subject
Anything that can have a history:
- People: clients, employees, suppliers
- Things: policies, contracts, assets
- Processes: claims, cases, projects

**Industry-agnostic** - meaning is defined by configuration, not code.

### 3. Event
An **immutable fact** about what happened:
- Timestamped precisely
- Cryptographically chained (like Git commits)
- Never modified or deleted
- Industry-neutral structure
- Rich semantic payload

### 4. Document
Versioned evidence linked to events:
- Uploaded files, generated reports, emails
- Immutable and versioned
- Checksummed for integrity
- Always linked to events

---

## Cryptographic Integrity

Each event is hashed from:
```
SHA-256(
  tenant_id +
  subject_id +
  event_type +
  event_time +
  canonical_json(payload) +
  previous_hash
)
```

**Result**: Per-subject blockchain-style chains
- First event: `previous_hash = "GENESIS"`
- Each subsequent event: `previous_hash = <last_event_hash>`
- Tampering breaks the chain and is immediately detectable

---

## Architecture

### Multi-Tenant SaaS
- **Logical Isolation**: `tenant_id` on all tables
- **Row-Level Security**: PostgreSQL RLS (Phase 2)
- **API Isolation**: All queries tenant-scoped via `x-tenant-id` header

### SOLID Principles
- **Single Responsibility**: Models, repos, services, schemas separated
- **Open/Closed**: HashService extensible (SHA256, SHA512, etc.)
- **Liskov Substitution**: BaseRepository common interface
- **Interface Segregation**: Clean protocols for dependencies
- **Dependency Inversion**: Services depend on abstractions

### Event Sourcing
- **Append-Only**: Events never updated/deleted
- **State Derivation**: Current state computed from event log
- **Temporal Queries**: Reconstruct state at any point in time

---

## Technology Stack

**Backend**:
- Python 3.12 + FastAPI
- PostgreSQL 15+ (JSONB, asyncpg)
- SQLAlchemy 2.0 (async)
- Pydantic 2.0 (validation)

**Security**:
- Cryptographic event chaining
- Multi-tenant isolation
- Immutable audit trails

**Deployment**:
- Docker + Kubernetes
- PostgreSQL (RDS/managed)
- S3/MinIO for documents

---

## Quick Start

### Prerequisites
```bash
# PostgreSQL 14+
brew install postgresql@14
brew services start postgresql@14

# Python 3.12+
conda create -n timeline python=3.12
conda activate timeline
```

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Setup database
createdb timeline_db
createuser timeline_user

# Configure
cp .env.example .env
# Edit .env with your settings
```

### Run
```bash
# Start server
uvicorn main:app --reload

# Server runs at http://localhost:8000
# API docs at http://localhost:8000/docs
```

---

## API Overview

### Tenants
```
POST   /tenants              # Create tenant
GET    /tenants/{id}         # Get tenant
GET    /tenants              # List tenants
PUT    /tenants/{id}         # Update tenant
PATCH  /tenants/{id}/status  # Update status
```

### Subjects
```
POST   /subjects             # Create subject
GET    /subjects/{id}        # Get subject
GET    /subjects             # List subjects (supports ?subject_type=CLIENT)
PUT    /subjects/{id}        # Update subject
DELETE /subjects/{id}        # Delete subject

Header: x-tenant-id (required)
```

### Events
```
POST   /events               # Create event (cryptographically chained)

Header: x-tenant-id (required)
```

### Documents
```
POST   /documents                    # Upload document
GET    /documents/{id}               # Get document
GET    /documents/subject/{id}       # Get all docs for subject
GET    /documents/event/{id}         # Get all docs for event
GET    /documents/{id}/versions      # Version history
PUT    /documents/{id}               # Update metadata
DELETE /documents/{id}               # Soft delete

Header: x-tenant-id (required)
```

---

## Example Usage

### 1. Create a Tenant
```bash
curl -X POST http://localhost:8000/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "code": "acme-corp",
    "name": "Acme Corporation",
    "status": "active"
  }'
```

### 2. Create a Subject
```bash
curl -X POST http://localhost:8000/subjects \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: <tenant_id>" \
  -d '{
    "subject_type": "CLIENT",
    "external_ref": "CLIENT-001"
  }'
```

### 3. Create an Event
```bash
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: <tenant_id>" \
  -d '{
    "subject_id": "<subject_id>",
    "event_type": "CLIENT_ONBOARDED",
    "event_time": "2024-12-13T10:00:00Z",
    "payload": {
      "name": "John Doe",
      "email": "john@example.com",
      "tier": "premium"
    }
  }'

# Returns: Event with cryptographic hash and chain linkage
```

### 4. Upload Evidence Document
```bash
curl -X POST http://localhost:8000/documents \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: <tenant_id>" \
  -d '{
    "subject_id": "<subject_id>",
    "event_id": "<event_id>",
    "document_type": "CONTRACT",
    "filename": "contract.pdf",
    "original_filename": "Acme_Contract_2024.pdf",
    "mime_type": "application/pdf",
    "file_size": 102400,
    "checksum": "<sha256_hash>",
    "storage_ref": "s3://bucket/path/to/file.pdf"
  }'
```

---

## Use Cases

### Regulatory Compliance
- **Insurance**: Policy management, claims, compliance trails
- **Healthcare**: HIPAA-compliant patient histories
- **Finance**: SOC 2, audit trails, transaction history

### Legal Evidence
- **Cryptographically verified** timeline of events
- **Tamper-proof** audit trails admissible as evidence
- **Complete history** with document attachments

### Enterprise Integration
- **Unified timeline** from CRM, ERP, support systems
- **Single source of truth** across departments
- **Cross-system** event correlation

### State Reconstruction
- **Time-travel queries**: What was the state at any point?
- **Event replay**: Rebuild current state from history
- **Audit forensics**: Trace exactly what happened when

---

## Project Status

### ✅ Phase 1 Complete (Core Platform)
- Multi-tenant data model
- Cryptographic event chaining
- SOLID architecture implementation
- Complete CRUD APIs
- PostgreSQL with asyncpg
- Pydantic validation

### 🚧 Phase 2 (Configuration Layer)
- Schema registry for payload validation
- Subject/event type configuration
- Workflow engine
- Row-level security (RLS)
- Chain verification API

### 📋 Phase 3 (Advanced Features)
- State derivation queries
- Timeline visualization
- Actor tracking
- Materialized views
- Performance optimizations

---

## Development

### Project Structure
```
timeline/
├── api/              # FastAPI endpoints
├── core/             # Database, config, protocols
├── domain/           # Entities, value objects
├── models/           # SQLAlchemy ORM models
├── repositories/     # Data access layer
├── schemas/          # Pydantic validation schemas
├── services/         # Business logic
└── utils/            # Utilities
```

### Key Files
- `models/*.py` - Database models (Tenant, Subject, Event, Document)
- `repositories/*.py` - Data access with BaseRepository (LSP)
- `services/hash_service.py` - Cryptographic hashing (OCP)
- `core/protocols.py` - Interface definitions (DIP)
- `domain/` - Domain entities and value objects (SRP)

---

## Design Principles

1. **Events are Truth** - Documents are evidence, events are facts
2. **Immutability** - History cannot be changed
3. **Configuration > Code** - Industry logic via config, not hard-coding
4. **Multi-Tenant First** - Complete isolation by design
5. **Cryptographic Proof** - Mathematical verification of integrity
6. **SOLID Architecture** - Maintainable, extensible, testable

---

## License

[Your License Here]

## Documentation

- [Full Specification](docs/timeline.md)
- [Technical Specification](docs/Technical_Specification.md)
- [API Documentation](http://localhost:8000/docs) (when running)

---

## Contributing

Timeline is an open architecture for enterprise memory. Contributions welcome.

**Key Innovation**: Making business events immutable and cryptographically verifiable - creating an organizational "black box" that can prove what happened, when, and in what order.
