# Timeline System - Architecture Guide

**For developers, collaborators, and new team members**

This guide explains how Timeline's core models work together to create a multi-tenant, cryptographically-secured event sourcing system.

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Models Explained](#core-models-explained)
3. [How Models Work Together](#how-models-work-together)
4. [Multi-Tenancy Architecture](#multi-tenancy-architecture)
5. [Cryptographic Integrity](#cryptographic-integrity)
6. [Real-World Examples](#real-world-examples)
7. [Implementation Status](#implementation-status)
8. [Contributing Ideas](#contributing-ideas)

---

## System Overview

Timeline is a **system of record for enterprise history** that captures *what happened, to whom, when, by whom, and with what evidence* — immutably and traceably.

**Core Philosophy**:
- **Events** are the source of truth (immutable, append-only)
- **Current state** is derived from events, never stored directly
- **Multi-tenant** by design - complete data isolation
- **Industry-agnostic** - configured via schemas, not hardcoded logic
- **Cryptographically secured** - blockchain-style event chaining

---

## Core Models Explained

### 1. Tenant - Organization Isolation

**What it is**: Represents an organization using the Timeline system

**Why it exists**:
- Foundation for multi-tenancy - every organization is a separate tenant
- Data isolation boundary - all data is scoped by `tenant_id`
- Configuration owner - each tenant defines its own event types, schemas, workflows

**Key Fields**:
```python
id              # Unique tenant identifier (CUID)
code            # Human-readable code (e.g., "acme-corp", "hospital-a")
name            # Organization display name
status          # "active" | "suspended"
created_at      # Timestamp
updated_at      # Timestamp
```

**Real-world analogy**: Like separate companies in a SaaS platform - Acme Corp and Hospital A both use Timeline but never see each other's data.

**Database Model**: [models/tenant.py](../models/tenant.py)

---

### 2. User - Authentication & Access Control

**What it is**: People who authenticate and interact with the Timeline API

**Why it exists**:
- Authentication layer - JWT-based login with bcrypt password hashing
- Tenant membership - users belong to a specific tenant
- Future RBAC foundation - will be linked to roles/permissions (planned)

**Key Fields**:
```python
id              # User identifier (CUID)
tenant_id       # Links user to their organization
username        # Login username (unique within tenant)
email           # Email address (unique within tenant)
hashed_password # Bcrypt-hashed password
is_active       # Account status (true/false)
created_at      # Timestamp
updated_at      # Timestamp
```

**Security Features**:
- Passwords hashed with bcrypt (never stored plaintext)
- JWT tokens contain both `user_id` and `tenant_id`
- Username and email unique **within tenant** (not globally)
- Soft delete via `is_active` flag

**Real-world analogy**: Employees of Acme Corp who log into the system to record events or view history.

**Database Model**: [models/user.py](../models/user.py)

---

### 3. Subject - "The Who/What"

**What it is**: Anything that can have a history - the entity events happen to

**Why it exists**:
- Industry-agnostic entity - can represent clients, policies, contracts, employees, assets, etc.
- Timeline anchor - all events are attached to a subject
- Type-driven flexibility - `subject_type` defines what it represents (configuration, not code)

**Key Fields**:
```python
id              # Subject identifier (CUID)
tenant_id       # Tenant isolation
subject_type    # What kind of thing (e.g., "client", "policy", "employee")
external_ref    # Optional business identifier (e.g., "POL-12345")
created_at      # Timestamp
```

**Industry Examples**:

| Industry | Subject Type | External Ref | Events |
|----------|-------------|--------------|--------|
| Insurance | Policy | POL-12345 | issued, premium_paid, claim_filed |
| Healthcare | Patient | PAT-789 | admitted, discharged, test_ordered |
| HR | Employee | EMP-456 | hired, promoted, terminated |
| Finance | Account | ACC-999 | opened, deposit, withdrawal |

**Key Design Principle**: No hardcoded subject types in code. Each tenant defines their own via configuration.

**Database Model**: [models/subject.py](../models/subject.py)

---

### 4. Event - "What Happened" (Source of Truth)

**What it is**: Immutable record of something that happened - the **core** of the entire system

**Why it exists**:
- **Immutable audit trail** - append-only, never updated or deleted
- **Cryptographic chain** - each event hashes itself + previous event (blockchain-style integrity)
- **Industry-neutral facts** - records "what happened" without business logic
- **Source of truth** - current state is derived from events, never stored

**Key Fields**:
```python
id              # Event identifier (CUID)
tenant_id       # Tenant isolation
subject_id      # Which entity this happened to
event_type      # What kind of event (e.g., "payment_received")
event_time      # When it happened (NOT when recorded - supports backdating)
payload         # JSON data with event details (validated by EventSchema if exists)
hash            # SHA-256 hash of this event
previous_hash   # Links to previous event in subject's chain (NULL for genesis)
created_at      # When event was recorded
```

**Immutability Guarantees**:
- No UPDATE operations allowed
- No DELETE operations allowed
- Ordered by `event_time`
- Hash links events per subject (cryptographic chain)

**Why Events Must Be Immutable**:
1. **Compliance**: Regulatory requirements demand unchangeable audit trails
2. **Trust**: History cannot be silently rewritten
3. **Debugging**: Always know exactly what happened when
4. **Legal**: Events are legally admissible evidence

**Cryptographic Chaining**:
```
Subject: Policy #12345
┌─────────────────────────────────────────────────────────────┐
│ Event 1: policy_issued                                      │
│ hash: abc123...                                             │
│ previous_hash: NULL  ← Genesis event (first in chain)       │
└─────────────────────────────────────────────────────────────┘
              ↓ (linked by previous_hash)
┌─────────────────────────────────────────────────────────────┐
│ Event 2: premium_paid                                       │
│ hash: def456...                                             │
│ previous_hash: abc123...  ← Links to Event 1                │
└─────────────────────────────────────────────────────────────┘
              ↓ (linked by previous_hash)
┌─────────────────────────────────────────────────────────────┐
│ Event 3: claim_filed                                        │
│ hash: ghi789...                                             │
│ previous_hash: def456...  ← Links to Event 2                │
└─────────────────────────────────────────────────────────────┘
```

**Tampering Detection**: If someone tries to change Event 2's payload, its hash changes, breaking the chain at Event 3 → tampering immediately detected!

**Example Event**:
```json
{
  "subject_id": "policy_12345",
  "event_type": "premium_paid",
  "event_time": "2025-01-15T10:00:00Z",
  "payload": {
    "amount": 500.00,
    "currency": "USD",
    "payment_method": "credit_card",
    "invoice_id": "INV-2025-001"
  }
}
```

**Database Model**: [models/event.py](../models/event.py)

---

### 5. EventSchema - Configuration Layer

**What it is**: Defines the expected structure and validation rules for event payloads

**Why it exists**:
- **Tenant-specific validation** - each tenant defines schemas for their event types
- **Data quality enforcement** - validates event payloads before they're stored
- **Schema evolution** - supports versioning (v1, v2, v3) for backward compatibility
- **Configuration over code** - industry meaning applied via schemas, not hardcoded logic

**Key Fields**:
```python
id              # Schema identifier (CUID)
tenant_id       # Tenant ownership
event_type      # Which event type this validates (e.g., "payment_received")
schema_json     # JSON Schema definition (standard format)
version         # Schema version number (1, 2, 3, ...)
is_active       # Whether this version is currently used
created_at      # Timestamp
updated_at      # Timestamp
```

**How It Works**:

1. **Schema Registration**: Tenant creates a schema for an event type
   ```json
   {
     "event_type": "payment_received",
     "version": 1,
     "schema_json": {
       "type": "object",
       "properties": {
         "amount": {"type": "number", "minimum": 0},
         "currency": {"type": "string", "enum": ["USD", "EUR", "GBP"]},
         "payment_method": {"type": "string"}
       },
       "required": ["amount", "currency"]
     }
   }
   ```

2. **Automatic Validation**: When creating an event with `event_type="payment_received"`:
   - System looks up active schema for that event type
   - Validates payload against JSON Schema
   - Rejects invalid payloads **before** computing hash

3. **Schema Evolution**: Supports backward-compatible versioning
   ```
   V1: { amount: number }
   V2: { amount: number, currency: string }  ← Added field
   V3: { amount: number, currency: string, tax: number }  ← Added field
   ```

**Benefits**:
- **Data Quality**: Invalid data never enters the system
- **Self-Documenting**: Schemas describe expected event structure
- **Tenant Flexibility**: Each tenant defines their own rules
- **Backward Compatible**: Old events remain valid when schema evolves

**Database Model**: [models/event_schema.py](../models/event_schema.py)
**API Endpoints**: [api/event_schemas.py](../api/event_schemas.py)

---

### 6. Document - Evidence Attachments

**What it is**: Files, PDFs, emails - evidence attached to events/subjects

**Why it exists**:
- **Evidence, not truth** - documents support events but events are the source of truth
- **External storage** - files stored in S3/MinIO, not database
- **Tamper detection** - checksum verification
- **Versioning** - documents can have multiple versions
- **Compliance** - soft delete ensures nothing is truly lost

**Key Fields**:
```python
id              # Document identifier (CUID)
tenant_id       # Tenant isolation
subject_id      # Links to subject
event_id        # Optional link to specific event
document_type   # Kind of document (e.g., "invoice", "contract")
filename        # Original filename
storage_ref     # S3 path/URL to actual file
checksum        # SHA-256 hash for tamper detection
version         # Version number
deleted_at      # Soft delete timestamp (compliance - never hard delete)
created_at      # Timestamp
updated_at      # Timestamp
```

**Document Lifecycle**:
```
1. Upload → Store in S3 → Compute checksum
2. Create Document record with storage_ref
3. Link to Event and/or Subject
4. Soft delete when no longer needed (deleted_at set, never removed from DB/S3)
```

**Example Usage**:
```
Event: "claim_filed"
Document: Scanned accident report PDF
  - storage_ref: s3://timeline-docs/acme-corp/claims/accident-report-123.pdf
  - checksum: sha256:abc123def456...
  - document_type: "accident_report"
```

**Database Model**: [models/document.py](../models/document.py)

---

### 7. Workflow - Event-Driven Automation

**What it is**: Automated actions triggered when specific events occur

**Why it exists**:
- **Business process automation** - reduce manual steps and human error
- **Event-driven architecture** - actions happen automatically based on events
- **Tenant-configurable** - each tenant defines their own workflows
- **Audit trail** - all workflow executions are logged for compliance
- **Conditional logic** - workflows only trigger when conditions are met

**Key Models**:

#### Workflow (Configuration)
```python
id                      # Workflow identifier (CUID)
tenant_id              # Tenant ownership
name                   # Human-readable name
description            # What this workflow does
trigger_event_type     # Event type that triggers this workflow
trigger_conditions     # Optional JSON conditions (payload field matching)
actions                # Array of actions to execute
is_active              # Enable/disable workflow
execution_order        # Priority when multiple workflows match
max_executions_per_day # Rate limiting (optional)
created_at             # Timestamp
updated_at             # Timestamp
deleted_at             # Soft delete
```

#### WorkflowExecution (Audit Trail)
```python
id                        # Execution identifier (CUID)
tenant_id                 # Tenant ownership
workflow_id               # Which workflow executed
triggered_by_event_id     # Event that triggered execution
triggered_by_subject_id   # Subject of triggering event
status                    # pending | running | completed | failed
started_at                # Execution start time
completed_at              # Execution end time
actions_executed          # Count of successful actions
actions_failed            # Count of failed actions
execution_log             # Detailed JSON log of each action
error_message             # Error if execution failed
created_at                # Timestamp
```

**How It Works**:

1. **Workflow Creation**: Tenant configures automated response to events
   ```json
   POST /workflows/
   {
     "name": "Auto-escalate urgent issues",
     "trigger_event_type": "issue_created",
     "trigger_conditions": {
       "payload.priority": "urgent"
     },
     "actions": [
       {
         "type": "create_event",
         "params": {
           "event_type": "issue_escalated",
           "payload": {
             "escalated_by": "workflow",
             "reason": "auto_urgent"
           }
         }
       }
     ]
   }
   ```

2. **Automatic Triggering**: When matching event is created
   ```
   User creates event → EventService.create_event()
                     ↓
   Event stored → Hash computed and validated
                     ↓
   WorkflowEngine.process_event_triggers()
                     ↓
   Find matching workflows (event_type + conditions)
                     ↓
   Execute actions (create events, send notifications, etc.)
                     ↓
   Log execution results in WorkflowExecution table
   ```

3. **Condition Evaluation**: Simple payload field matching
   ```python
   # Workflow triggers only if payload.priority == "urgent"
   trigger_conditions = {
     "payload.priority": "urgent"
   }

   # No conditions = always trigger for this event type
   trigger_conditions = None
   ```

4. **Supported Actions** (MVP):
   - `create_event`: Creates a new event on the same subject
   - More action types can be added (notifications, webhooks, etc.)

**Example Workflow Scenarios**:

**Insurance Claims Processing**:
```json
{
  "name": "Auto-assign claims adjuster",
  "trigger_event_type": "claim_filed",
  "trigger_conditions": {
    "payload.claim_type": "accident"
  },
  "actions": [{
    "type": "create_event",
    "params": {
      "event_type": "adjuster_assigned",
      "payload": {
        "adjuster_id": "auto_pool",
        "assignment_type": "automatic"
      }
    }
  }]
}
```

**HR Onboarding**:
```json
{
  "name": "Start background check",
  "trigger_event_type": "offer_accepted",
  "actions": [{
    "type": "create_event",
    "params": {
      "event_type": "background_check_initiated",
      "payload": {
        "vendor": "screening_service",
        "initiated_by": "workflow"
      }
    }
  }]
}
```

**Security Features**:
- **Infinite loop prevention**: Workflow-created events don't trigger workflows by default
- **Error isolation**: Workflow failures don't fail the original event creation
- **Rate limiting**: Optional `max_executions_per_day` prevents runaway workflows
- **Audit trail**: Every execution logged with detailed results

**Integration with Event System**:
- Workflows trigger **after** event is successfully created
- EventService → WorkflowEngine (via dependency injection)
- WorkflowEngine receives EventService reference to create follow-up events
- All workflow-created events use `trigger_workflows=False` to prevent loops

**Database Models**:
- [models/workflow.py](../models/workflow.py)
- [services/workflow_engine.py](../services/workflow_engine.py)
- [repositories/workflow_repo.py](../repositories/workflow_repo.py)

**API Endpoints**: [api/workflows.py](../api/workflows.py)

---

## How Models Work Together

### Complete Flow: Insurance Policy Payment

Let's walk through a real example of how all models interact:

#### 1. Setup (One-time)
```
Tenant: "acme-insurance" (insurance company)
User: alice@acme-insurance.com (customer service rep)
Subject: Policy #POL-12345 (the insurance policy)
```

#### 2. Define Event Schema
```json
POST /event-schemas/
{
  "event_type": "premium_paid",
  "version": 1,
  "schema_json": {
    "type": "object",
    "properties": {
      "amount": {"type": "number", "minimum": 0},
      "currency": {"type": "string", "enum": ["USD", "EUR"]},
      "payment_method": {"type": "string"},
      "invoice_id": {"type": "string"}
    },
    "required": ["amount", "currency", "payment_method"]
  }
}
```

#### 3. Record Payment Event
```json
POST /events/
{
  "subject_id": "pol-12345",
  "event_type": "premium_paid",
  "event_time": "2025-01-15T10:00:00Z",
  "payload": {
    "amount": 500.00,
    "currency": "USD",
    "payment_method": "credit_card",
    "invoice_id": "INV-2025-001"
  }
}
```

**What Happens Internally**:
1. ✅ **Authentication**: JWT token validated → user = alice, tenant = acme-insurance
2. ✅ **Schema Validation**: Payload validated against "premium_paid" schema
3. ✅ **Chain Lookup**: Get previous hash for POL-12345 (or NULL if genesis)
4. ✅ **Hash Computation**: SHA-256 hash of (tenant_id + subject_id + event_type + event_time + payload + previous_hash)
5. ✅ **Event Creation**: Immutably stored with cryptographic link to previous event
6. ✅ **Return**: Event with hash confirmation

#### 4. Attach Supporting Document
```json
POST /documents/
{
  "subject_id": "pol-12345",
  "event_id": "evt-abc123",
  "document_type": "payment_receipt",
  "filename": "receipt-2025-001.pdf",
  "storage_ref": "s3://timeline-docs/acme-insurance/receipts/2025-001.pdf",
  "checksum": "sha256:def456..."
}
```

#### 5. Query Timeline (Derive Current State)
```json
GET /events/subject/pol-12345

Response:
[
  {
    "event_type": "policy_issued",
    "event_time": "2024-01-01T09:00:00Z",
    "hash": "aaa111...",
    "previous_hash": null  // Genesis event
  },
  {
    "event_type": "premium_paid",
    "event_time": "2025-01-15T10:00:00Z",
    "payload": { "amount": 500.00, "currency": "USD" },
    "hash": "bbb222...",
    "previous_hash": "aaa111..."  // Links to policy_issued
  }
]
```

**Current State Derivation**:
```
Policy Status = Last "policy_status_changed" event → "active"
Balance Paid = SUM of all "premium_paid" amounts → $500.00
Outstanding Claims = COUNT of "claim_filed" - COUNT of "claim_settled" → 0
```

---

## Multi-Tenancy Architecture

### Isolation Strategy

**Every table has `tenant_id`** - no exceptions!

```sql
-- All queries automatically scoped
SELECT * FROM event WHERE tenant_id = current_user.tenant_id

-- Cross-tenant access prevented at multiple layers:
1. JWT token contains tenant_id
2. Database queries filter by tenant_id
3. Foreign keys enforce CASCADE DELETE on tenant removal
```

### Tenant Isolation Example

```
Acme Insurance (tenant_id: aaaa)
├── Users: alice@acme, bob@acme
├── Subjects: POL-12345, POL-67890
└── Events: policy_issued, premium_paid

Hospital Corp (tenant_id: bbbb)
├── Users: charlie@hospital, diana@hospital
├── Subjects: PAT-001, PAT-002
└── Events: patient_admitted, test_ordered
```

**Security Guarantees**:
- Alice@acme **cannot** see Hospital Corp's patients
- Charlie@hospital **cannot** see Acme's policies
- Database enforces isolation even if application code fails

---

## Cryptographic Integrity

### SHA-256 Event Chaining

Each event includes:
```
hash = SHA256(
  tenant_id +
  subject_id +
  event_type +
  event_time +
  JSON.stringify(payload) +
  previous_hash
)
```

### Verification Process

```python
def verify_chain(subject_id: str) -> bool:
    events = get_events_for_subject(subject_id)

    for i, event in enumerate(events):
        # Recompute hash
        computed = compute_hash(
            event.tenant_id,
            event.subject_id,
            event.event_type,
            event.event_time,
            event.payload,
            events[i-1].hash if i > 0 else None
        )

        # Verify hash matches
        if computed != event.hash:
            return False  # Tampering detected!

        # Verify chain link
        if i > 0 and event.previous_hash != events[i-1].hash:
            return False  # Chain broken!

    return True  # Chain valid!
```

### Tamper Detection Scenarios

| Scenario | Detection Method |
|----------|-----------------|
| Event payload modified | Hash doesn't match recomputed value |
| Event deleted from middle | Next event's `previous_hash` points to missing event |
| Event inserted into middle | Hash chain breaks at insertion point |
| Events reordered | Hash chain breaks (previous_hash mismatch) |

---

## Real-World Examples

### Example 1: Healthcare Patient Timeline

**Setup**:
```json
Tenant: "city-hospital"
Subject: Patient #PAT-12345 (subject_type: "patient")
```

**Event Schema**:
```json
{
  "event_type": "test_ordered",
  "schema_json": {
    "properties": {
      "test_name": {"type": "string"},
      "ordering_physician": {"type": "string"},
      "urgency": {"type": "string", "enum": ["routine", "urgent", "stat"]}
    }
  }
}
```

**Timeline**:
```
2025-01-10: patient_admitted
  └─> Document: Admission form PDF

2025-01-11: test_ordered
  └─> payload: { test_name: "Blood Panel", urgency: "routine" }

2025-01-12: test_completed
  └─> Document: Lab results PDF
  └─> payload: { test_name: "Blood Panel", results_ref: "LAB-001" }

2025-01-15: patient_discharged
  └─> Document: Discharge summary PDF
```

---

### Example 2: Employee Lifecycle

**Setup**:
```json
Tenant: "tech-startup"
Subject: Employee #EMP-456 (subject_type: "employee")
```

**Timeline**:
```
2024-01-15: employee_hired
  └─> payload: { position: "Senior Developer", salary: 120000 }
  └─> Document: Signed offer letter

2024-07-01: salary_adjusted
  └─> payload: { new_salary: 130000, reason: "performance" }

2024-12-01: promoted
  └─> payload: { new_position: "Lead Developer" }

2025-02-01: employee_terminated
  └─> payload: { reason: "resignation", notice_period: 14 }
  └─> Document: Resignation letter
```

**Current State Derivation**:
```
Employment Status = Last event type → "terminated"
Current Salary = Last "salary_adjusted" or "employee_hired" → $130,000
Current Position = Last "promoted" or "employee_hired" → "Lead Developer"
```

---

## Implementation Status

Based on the design document ([docs/timeline.md](timeline.md)), here's the current implementation status:

| Feature | Status | Notes |
|---------|--------|-------|
| **Multi-Tenancy** | ✅ Complete | Tenant model, isolation, tenant-scoped queries |
| **User Authentication** | ✅ Complete | JWT, bcrypt, tenant-scoped users |
| **Subject Management** | ✅ Complete | Subject model, tenant-scoped types |
| **Event Sourcing** | ✅ Complete | Immutable events, append-only |
| **Cryptographic Chaining** | ✅ Complete | SHA-256 hashing, chain validation, verification endpoints |
| **Schema Registry** | ✅ Complete | EventSchema model, JSON Schema validation |
| **Event GET Endpoints** | ✅ Complete | Query by subject, type, tenant |
| **Document Storage** | ✅ Complete | Local filesystem storage with S3 abstraction ready |
| **RBAC System** | ✅ Complete | Roles, permissions, user roles, authorization service |
| **Workflows** | ✅ Complete | Event-driven automation with triggers and actions |
| **Performance Optimization** | ❌ Not Started | Caching, materialized views |
| **Compliance Features** | ❌ Not Started | GDPR, audit logs, retention policies |

### Next Priority Steps

Based on [docs/progress-report.md](progress-report.md):

1. ✅ **Schema Registry** - Complete
2. ✅ **RBAC** - Complete (roles, permissions, authorization)
3. ✅ **Chain Verification** - Complete (tamper detection endpoints)
4. ✅ **Document Storage** - Complete (local storage with S3-ready abstraction)
5. ✅ **Workflows** - Complete (event-driven automation MVP)
6. **Performance** - Redis caching + materialized views
7. **Compliance** - GDPR features (data export, deletion, retention)

---

## Contributing Ideas

We welcome contributions and ideas! Here's how you can help:

### Understanding the Codebase

**Key Files to Read**:
1. [docs/timeline.md](timeline.md) - Original design document
2. [models/](../models/) - Database models
3. [api/](../api/) - REST API endpoints
4. [services/](../services/) - Business logic
5. [repositories/](../repositories/) - Data access layer

**Architecture Principles**:
- **SOLID** - Single Responsibility, Dependency Inversion
- **DDD** - Domain-Driven Design with value objects
- **Clean Architecture** - Domain → Repository → Service → API layers
- **Dependency Injection** - FastAPI's `Depends()` pattern

### Areas for Contribution

**High Priority**:
- [ ] Redis caching layer
- [ ] Materialized views for performance
- [ ] GDPR compliance features (data export, deletion)
- [ ] S3 document storage backend (abstraction ready)
- [ ] Workflow action types (notifications, webhooks)

**Medium Priority**:
- [ ] Audit log enhancements
- [ ] API rate limiting
- [ ] OpenAPI documentation improvements
- [ ] Workflow rate limiting and scheduling
- [ ] Enhanced chain verification (batch processing)

**Nice to Have**:
- [ ] GraphQL API layer
- [ ] Event replay functionality
- [ ] Time-travel queries ("show state at timestamp X")
- [ ] Event projections/aggregations
- [ ] Admin UI

### Suggesting New Ideas

When proposing new features, consider:

1. **Multi-tenant compatibility** - Does it work for all tenants?
2. **Immutability** - Does it preserve event immutability?
3. **Industry-agnostic** - Is it configured, not hardcoded?
4. **Backward compatible** - Will existing data still work?
5. **Security** - Does it maintain tenant isolation?

**Discussion Format**:
```markdown
## Feature Proposal: [Name]

**Problem**: What problem does this solve?

**Solution**: How does it work?

**Multi-Tenancy**: How does it handle multiple tenants?

**Schema Impact**: Any new database tables/fields?

**API Changes**: New endpoints or modifications?

**Example Usage**: Code example showing how it's used
```

### Questions?

- **Architecture questions**: Review [docs/timeline.md](timeline.md)
- **Implementation details**: Check code comments in [models/](../models/), [services/](../services/)
- **API usage**: See [README.md](../README.md) getting started section
- **Database schema**: Check [alembic/versions/](../alembic/versions/) for migrations

---

## Appendix: Quick Reference

### Model Relationships

```
Tenant (1) ──< User (N)
Tenant (1) ──< Subject (N)
Tenant (1) ──< Event (N)
Tenant (1) ──< EventSchema (N)
Tenant (1) ──< Document (N)

Subject (1) ──< Event (N)
Event (1) ──< Document (N)

Event (1) ───> Event (1) [previous_hash chain]
```

### API Endpoints

```
POST   /auth/token           # Login
POST   /users/register       # Register user

POST   /tenants/             # Create tenant
GET    /tenants/{id}         # Get tenant

POST   /subjects/            # Create subject
GET    /subjects/{id}        # Get subject

POST   /events/              # Create event (with validation)
GET    /events/{id}          # Get event
GET    /events/subject/{id}  # Get subject timeline

POST   /event-schemas/       # Create schema
GET    /event-schemas/       # List schemas
GET    /event-schemas/event-type/{type}/active  # Get active schema

POST   /documents/           # Upload document
GET    /documents/{id}       # Get document metadata
```

### File Structure

```
timeline/
├── models/          # Database models (SQLAlchemy)
├── schemas/         # API schemas (Pydantic)
├── repositories/    # Data access layer
├── services/        # Business logic
├── api/            # REST endpoints
├── core/           # Config, database, auth
├── domain/         # Value objects, entities
├── alembic/        # Database migrations
└── docs/           # Documentation (you are here!)
```

---

**Last Updated**: December 2025
**For Questions**: Review design doc or check code comments
**Contributing**: See "Contributing Ideas" section above
