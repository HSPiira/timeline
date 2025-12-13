# Timeline System – Core-Concept Redesign (Multi-Tenant, Cross-Industry)

## 1. Core Concept (Reaffirmed)

Timeline is a **system of record for enterprise history**.

It captures *what happened, to whom, when, by whom, and with what evidence* — immutably and traceably.

### 1.1 Core Idea

The system is an **event-centric, multi-tenant enterprise timeline**.

**Fundamental principles**:
- Everything that happens is recorded as an **event**
- Events are immutable and append-only
- Documents are **evidence attached to events**
- "Current state" is **derived**, never stored as truth
- Industry meaning is applied via **configuration**, not code

This applies equally to:
- clients
- suppliers
- hospitals
- insurers
- employees
- contracts
- assets
- policies
- claims

### 1.2 System Characteristics

Timeline is:
- **Industry-agnostic** at its core
- **Multi-tenant** by design
- **Configurable** rather than hard-coded
- **Immutable** with cryptographic guarantees
- Suitable for **regulated, privacy-sensitive** organisations

Timeline does **not** try to model full business logic of every industry. Instead, it models **facts and events** emitted by business processes.

---

## 2. Multi-Tenancy First Principles

### 2.1 Tenant = Organisation

Every organisation using Timeline is a **tenant**.

A tenant:
- owns its data exclusively
- defines its own subjects, events, documents, and workflows
- has isolated access control

No data is shared across tenants unless explicitly configured (rare, controlled cases).

**Database Structure**:
```sql
tenant
------
id              UUID (PK)
code            TEXT UNIQUE
name            TEXT
status          TEXT  -- active | suspended
created_at      TIMESTAMP
```

**Rules**:
- All data is scoped to a tenant
- No cross-tenant access
- One deployment → many tenants

---

### 2.2 Isolation Model (Recommended)

**Logical isolation with hard guards**:

- `tenant_id` present on all core tables
- row-level security enforced at DB level
- tenant-scoped encryption keys
- tenant-aware caching (Redis namespaces)

This allows:
- lower operational cost
- easier onboarding of new organisations
- strong security guarantees

Physical isolation (separate DBs) can be added later for high-risk clients.

### 2.3 Isolation Strategy

**Single Database Approach**:
- Single PostgreSQL database
- `tenant_id` on every table
- Row-level security (PostgreSQL RLS)
- Enforced at multiple layers (database + application)

**Encryption**:
- Data at rest per tenant
- Separate object storage buckets if required
- Tenant-specific encryption keys (optional)

---

## 3. Canonical Data Model (Industry-Neutral)

These tables exist in **every deployment**, regardless of industry.

### 3.1 Tenant

Represents an organisation.

Fields:
- id
- name
- industry (label only, not logic)
- configuration set

(See database schema in section 2.1)

---

### 3.2 Subject (The "Who / What")

A subject is **anything that can have a history**.

**Examples**:
- client
- supplier
- employee
- policy
- contract
- asset
- claim
- hospital
- insurer

Subjects are:
- tenant-scoped
- type-driven
- extensible via configuration

**Database Schema**:
```sql
subject
-------
id              UUID (PK)
tenant_id       UUID (FK → tenant.id)
subject_type    TEXT   -- e.g. client, policy, supplier
external_ref    TEXT   -- optional business ID
created_at      TIMESTAMP
```

**Rules**:
- Subjects are **industry-agnostic**
- `subject_type` meaning is defined by tenant configuration
- No hard-coded subject types in code

---

### 3.3 Event (The "What Happened")

An event is an **immutable fact** — the **source of truth**.

**Core fields**:
- id
- tenant_id
- subject_id
- event_type
- timestamp
- actor
- payload (JSON)
- hash
- previous_hash

No industry semantics exist at this level.

**Database Schema**:
```sql
event
-----
id              UUID (PK)
tenant_id       UUID (FK → tenant.id)
subject_id      UUID (FK → subject.id)
event_type      TEXT
event_time      TIMESTAMP
payload         JSONB
previous_hash   TEXT
hash            TEXT
actor_id        UUID NULL
created_at      TIMESTAMP
```

**Rules**:
- Append-only
- No UPDATE operations allowed
- No DELETE operations allowed
- Ordered by event_time
- Hash links events per subject (cryptographic chain)

**Why Events are Immutable**:
1. Compliance: Regulatory requirements demand unchangeable audit trails
2. Trust: History cannot be silently rewritten
3. Debugging: Always know exactly what happened when
4. Legal: Events are legally admissible evidence

---

### 3.4 Document (The Evidence)

Documents are versioned, linked artifacts — **evidence, never truth**.

Examples:
- uploaded files
- generated PDFs
- emails
- scanned documents

Documents are:
- tenant-scoped
- linked to events and/or subjects
- versioned and immutable

**Database Schema**:
```sql
document
--------
id              UUID (PK)
tenant_id       UUID (FK → tenant.id)
subject_id      UUID (FK → subject.id)
event_id        UUID (FK → event.id)
document_type   TEXT
storage_ref     TEXT
checksum        TEXT
created_at      TIMESTAMP
```

**Rules**:
- Always linked to an event
- Stored externally (S3, MinIO, Azure Blob)
- Checksummed for tamper detection
- Version controlled

---

## 4. Event Hashing & Cryptographic Integrity

### 4.1 Purpose

Guarantee that:
- history cannot be altered silently
- timelines are provably ordered
- auditors can verify integrity
- tampering is immediately detectable

---

### 4.2 Hash Composition

Each event hash includes:

```
tenant_id
subject_id
event_type
event_time
canonical_payload
previous_hash
```

**Result**:
- Per-subject cryptographic chain (like blockchain)
- Independent timelines (no global bottleneck)
- Each subject has its own chain

---

### 4.3 Implementation Reference (Python)

```python
import hashlib
import json

def canonical_json(data: dict) -> str:
    """Ensure consistent JSON serialization for hashing"""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))

def compute_hash(parts: list[str]) -> str:
    """Compute SHA-256 hash from parts"""
    return hashlib.sha256("|".join(parts).encode()).hexdigest()

def calculate_event_hash(event):
    """Calculate hash for an event"""
    parts = [
        str(event.tenant_id),
        str(event.subject_id),
        event.event_type,
        event.event_time.isoformat(),
        canonical_json(event.payload),
        event.previous_hash or "GENESIS"
    ]
    return compute_hash(parts)
```

---

### 4.4 Genesis Rule

- First event per subject uses `GENESIS` as previous_hash
- All subsequent events must reference the last event's hash
- Breaking the chain is detectable

**Example Chain**:
```
Event 1: hash=abc123, previous_hash=GENESIS
Event 2: hash=def456, previous_hash=abc123
Event 3: hash=ghi789, previous_hash=def456

→ Any tampering of Event 2 changes its hash
→ Event 3's previous_hash no longer matches
→ Chain is broken and detectable
```

---

### 4.5 Chain Verification

**Verification Algorithm**:
```python
def verify_event_chain(subject_id: str) -> bool:
    events = get_events_for_subject(subject_id)  # Ordered by sequence

    previous_hash = "GENESIS"

    for event in events:
        # Check previous hash matches
        if event.previous_hash != previous_hash:
            return False

        # Recalculate hash and verify
        expected_hash = calculate_event_hash(event)
        if event.hash != expected_hash:
            return False

        previous_hash = event.hash

    return True
```

**When to Verify**:
- On demand (API endpoint)
- Scheduled jobs (daily integrity checks)
- Before critical operations
- Compliance audits

---

## 5. Configuration Layer (Where Industries Differ)

Each tenant configures:

### 5.1 Subject Types

Example:
- CLIENT
- SUPPLIER
- EMPLOYEE
- POLICY
- CLAIM
- ASSET

Each type defines:
- Display name
- Icon and color
- JSON schema for attributes
- Behavior flags (has_timeline, allow_documents)

---

### 5.2 Event Types

Example:
- ONBOARDED
- CONTRACT_SIGNED
- PAYMENT_RECEIVED
- CLAIM_SUBMITTED
- POLICY_RENEWED

Event types are purely declarative.

Each event type defines:
- Display name
- Category
- Payload schema (JSON Schema)
- Importance level
- Whether it's a milestone
- Workflow triggers

---

### 5.3 Payload Schemas

Each event type registers a schema:
- validated using Pydantic / JSON Schema
- tenant-specific
- versioned

This allows industries to capture exactly what they need.

**Example Event Schema**:
```json
{
  "event_type": "PAYMENT_RECEIVED",
  "version": 1,
  "schema": {
    "type": "object",
    "properties": {
      "amount": {
        "type": "number",
        "minimum": 0,
        "required": true
      },
      "currency": {
        "type": "string",
        "enum": ["USD", "EUR", "GBP"],
        "required": true
      },
      "payment_method": {
        "type": "string"
      },
      "invoice_id": {
        "type": "string"
      }
    }
  }
}
```

---

### 5.4 Document Categories

Example:
- CONTRACT
- INVOICE
- POLICY_SCHEDULE
- MEDICAL_REPORT
- KYC_DOCUMENT

Each category defines:
- Display name
- Metadata schema
- Retention policy
- Access level

---

## 6. Schema Registry (Configuration, Not Code)

### 6.1 Why It Exists

Without schemas:
- payloads drift over time
- hashes become meaningless
- multi-tenant safety breaks
- validation is impossible

**The schema registry enforces**:
- Structural consistency
- Data quality
- Forward/backward compatibility
- Multi-tenant isolation

---

### 6.2 Event Schema Table

```sql
event_schema
------------
id              UUID (PK)
tenant_id       UUID (FK → tenant.id)
event_type      TEXT
schema_json     JSONB
version         INT
is_active       BOOLEAN
created_at      TIMESTAMP
```

**Rules**:
- Tenant controls its schemas
- Versioned (v1, v2, v3...)
- Old events stay valid (backward compatible)
- New events use latest active schema

---

### 6.3 Validation Flow (FastAPI Example)

1. **Incoming event** received via API
2. **Lookup active schema** for event_type and tenant
3. **Validate payload** with Pydantic / JSON Schema
4. **Reject if invalid** (return 400 error)
5. **Hash → store** if valid

```python
from pydantic import ValidationError
import jsonschema

def validate_event_payload(tenant_id: str, event_type: str, payload: dict):
    # Get active schema
    schema = db.get_active_schema(tenant_id, event_type)

    if not schema:
        raise ValueError(f"No schema found for {event_type}")

    # Validate
    try:
        jsonschema.validate(instance=payload, schema=schema.schema_json)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Invalid payload: {e.message}")

    return True
```

---

### 6.4 Schema Evolution

**Versioning Strategy**:
- V1 → V2: Add optional fields (backward compatible)
- V2 → V3: Deprecate fields (mark as optional)
- Breaking changes: New event type

**Example Evolution**:
```
V1: { amount: number }
V2: { amount: number, currency: string }  // Added currency with default
V3: { amount: number, currency: string, tax: number }  // Added tax
```

Events store their schema version, so old events remain valid.

---

## 7. State Derivation (Never Store Current State)

### 7.1 Key Rule

**Never store "current state" as truth.**

Current state is **derived** from the event log.

---

### 7.2 Examples

**Policy Status**:
```
Current status = last event of type "policy_status_changed"
```

**Outstanding Balance**:
```
Balance = SUM(payment_received) - SUM(payment_refunded)
```

**Client Active**:
```
Active = EXISTS(client_onboarded) AND NOT EXISTS(client_offboarded)
```

---

### 7.3 Derivation Algorithm

```python
def get_current_state(subject_id: str) -> dict:
    events = get_events_for_subject(subject_id)

    state = initialize_empty_state()

    for event in events:
        state = apply_event(state, event)

    return state

def apply_event(state: dict, event: Event) -> dict:
    """Apply event to state based on event type"""
    if event.event_type == "CLIENT_ONBOARDED":
        state["status"] = "active"
    elif event.event_type == "PAYMENT_RECEIVED":
        state["balance"] += event.payload["amount"]
    elif event.event_type == "POLICY_CREATED":
        state["policies"].append(event.payload)
    # ... more event handlers

    return state
```

---

### 7.4 Materialized Views (Performance Optimization)

For performance, optionally create:
- **PostgreSQL materialized views**
- **Cached projections** (Redis)
- **Snapshots** (periodic state checkpoints)

**Important**: These are **always rebuildable** from events.

**Example Snapshot Table**:
```sql
subject_snapshot
----------------
subject_id      UUID (PK)
tenant_id       UUID (FK)
snapshot_at_event_id    UUID
snapshot_at_sequence    BIGINT
state_json      JSONB
created_at      TIMESTAMP
```

**Rebuild Strategy**:
```
State = Snapshot + Events since snapshot
```

This optimizes reads while maintaining event sourcing truth.

---

## 8. Access Control (RBAC)

### 8.1 Principle

Access is granted to:
- **subjects** (by type)
- **event types** (read/create)
- **documents** (by category)

Not to raw database tables.

---

### 8.2 Core Tables

```sql
role
----
id              UUID (PK)
tenant_id       UUID (FK)
role_name       TEXT
description     TEXT

permission
----------
id              UUID (PK)
permission_key  TEXT    -- e.g. "event.create.payment"
description     TEXT

role_permission
---------------
role_id         UUID (FK → role.id)
permission_id   UUID (FK → permission.id)

user_role
---------
user_id         UUID (FK → user.id)
role_id         UUID (FK → role.id)
```

---

### 8.3 Permission Examples

**Event Permissions**:
- `event.create.policy` — Can create policy events
- `event.view.payment` — Can view payment events
- `event.view.claim` — Can view claim events

**Document Permissions**:
- `document.view.contract` — Can view contracts
- `document.upload.invoice` — Can upload invoices
- `document.delete.kyc` — Can delete KYC documents

**Subject Permissions**:
- `subject.create.client` — Can create clients
- `subject.view.supplier` — Can view suppliers
- `subject.update.policy` — Can update policy attributes

---

### 8.4 Permission Enforcement

```python
def check_permission(user: User, permission: str) -> bool:
    user_permissions = get_user_permissions(user.id)
    return permission in user_permissions

def create_event(user: User, event_data: dict):
    permission = f"event.create.{event_data['event_type']}"

    if not check_permission(user, permission):
        raise PermissionError(f"User lacks permission: {permission}")

    # Proceed with event creation
    ...
```

---

## 9. Modules Reframed (Cross-Industry Safe)

### 9.1 What a Module Really Is

A module is **optional automation logic**, not a data model.

It:
- listens to events
- emits new events
- enforces cross-event rules
- integrates external systems

**Modules are event processors, not domain models.**

---

### 9.2 Core Modules (Shared by All Tenants)

- **Authentication & RBAC**
- **Timeline query & rendering**
- **Document storage**
- **Audit & compliance**
- **Event validation**
- **Schema management**

---

### 9.3 Domain Modules (Reusable Across Industries)

These are **horizontal**, not vertical:

- **Payment Tracking** (works for insurance, healthcare, retail, etc.)
- **Contract Lifecycle** (insurance, procurement, employment)
- **Notification & Escalation** (universal)
- **SLA Monitoring** (service industries)
- **Reconciliation** (finance, insurance, procurement)

Each works for many industries via configuration.

---

### 9.4 Industry-Specific Logic (Kept Minimal)

Only built when:
- automation is complex
- rules cannot be declarative
- integrations are specialised

Even then, logic emits neutral events.

**Example**: Insurance claims automation
- Input: `CLAIM_SUBMITTED` event
- Logic: Apply business rules (fraud detection, eligibility)
- Output: `CLAIM_APPROVED` or `CLAIM_REJECTED` event

The core system only sees events. Industry logic is pluggable.

---

## 10. Workflow Model (Declarative, Tenant-Owned)

Workflows are defined as:

```
IF event_type == X
AND conditions match payload
THEN emit event Y
OR notify role Z
```

No BPM engine.
No long-running orchestration.

This keeps workflows:
- auditable
- predictable
- portable across tenants

**Example Workflow**:
```json
{
  "name": "High-Value Claim Approval",
  "trigger_event_type": "CLAIM_SUBMITTED",
  "conditions": {
    "payload.claim_amount": { ">": 10000 }
  },
  "actions": [
    {
      "type": "emit_event",
      "event_type": "APPROVAL_REQUIRED",
      "payload_template": {
        "claim_id": "{{trigger_event.payload.claim_number}}",
        "amount": "{{trigger_event.payload.claim_amount}}"
      }
    },
    {
      "type": "notify",
      "role": "claims_manager",
      "template": "high_value_claim_submitted"
    }
  ]
}
```

**Execution**:
- Workflows execute immediately after event creation
- Synchronous (blocking) or asynchronous (queue)
- All workflow executions logged as events

---

## 11. API Architecture (Tenant-Aware)

All APIs are tenant-scoped:

```
POST   /tenants/{id}/events
GET    /tenants/{id}/timeline/{subject_id}
POST   /tenants/{id}/documents
POST   /tenants/{id}/schemas
GET    /tenants/{id}/subjects
```

Tenant context resolved via:
- auth token (JWT with tenant_id claim)
- request headers (X-Tenant-ID)
- subdomain (acme.timeline.app → tenant_slug = "acme")

**Enforcement**:
```
Request → Tenant Middleware → Set RLS Context → Process → Response
```

Every API call:
1. Extracts tenant_id
2. Sets PostgreSQL session variable
3. RLS filters all queries automatically
4. Application validates tenant_id matches

---

## 12. Security & Compliance (Enterprise-Grade)

### 12.1 Security Layers

- **Tenant-level RBAC** (section 8)
- **Immutable event ledger** (section 4)
- **Cryptographic chaining** (section 4)
- **Document access policies** (role-based)
- **Full auditability** (all actions logged as events)

### 12.2 Designed For

- **Insurance**: Policy management, claims, compliance
- **Healthcare**: HIPAA compliance, patient histories
- **Finance**: SOC 2, audit trails, transaction history
- **Procurement**: Contract lifecycle, supplier management
- **Legal**: Case management, evidence chains

### 12.3 Compliance Features

**GDPR**:
- Right to access (export subject data)
- Right to erasure (anonymize events, not delete)
- Right to portability (JSON/CSV export)
- Consent tracking (via events)

**HIPAA**:
- PHI encryption
- Access audit trails
- Minimum necessary access
- BAA compliance

**SOC 2**:
- Audit logging
- Access controls
- Encryption
- Monitoring

---

## 13. Industry Adaptation (No Module Explosion)

You **do not build new modules** per industry.

You configure:
- subject types
- event types
- schemas
- workflows

**Insurance, healthcare, procurement are configurations, not forks.**

**Example: Insurance Configuration**
```yaml
subject_types:
  - CLIENT
  - POLICY
  - CLAIM
  - PROVIDER

event_types:
  - CLIENT_ONBOARDED
  - POLICY_CREATED
  - POLICY_RENEWED
  - PAYMENT_RECEIVED
  - CLAIM_SUBMITTED
  - CLAIM_APPROVED
  - CLAIM_REJECTED

document_categories:
  - CONTRACT
  - POLICY_SCHEDULE
  - CLAIM_FORM
  - INVOICE
  - KYC
```

**Example: Healthcare Configuration**
```yaml
subject_types:
  - PATIENT
  - PROVIDER
  - EPISODE
  - APPOINTMENT

event_types:
  - PATIENT_REGISTERED
  - APPOINTMENT_SCHEDULED
  - MEDICATION_PRESCRIBED
  - LAB_RESULT_RECEIVED
  - EPISODE_CLOSED

document_categories:
  - CONSENT_FORM
  - LAB_REPORT
  - PRESCRIPTION
  - IMAGING
  - MEDICAL_RECORD
```

Same core system. Different configurations.

---

## 14. Deployment Model

Supported:
- **single tenant** (your organisation)
- **multi-tenant SaaS**
- **private cloud**
- **on-premise**

Same codebase.
Different isolation policies.

**Infrastructure Options**:
- PostgreSQL 15+ (with RLS)
- Redis (tenant-namespaced caching)
- S3 / MinIO / Azure Blob (document storage)
- Docker / Kubernetes (containerization)
- AWS / Azure / GCP (cloud hosting)

---

## 15. Why This Design Scales Across Industries

Because:
- industries differ in *meaning*, not in *facts*
- facts are events
- evidence is documents
- ownership is tenancy
- configuration beats code

Timeline records truth. Business interpretation sits above it.

**This makes Timeline**:
- Future-proof (new industries = new configs)
- Maintainable (one codebase)
- Compliant (immutable, auditable)
- Scalable (multi-tenant)
- Vendor-neutral (open architecture)

---

## 16. Final Architectural Position

Timeline is:
- a **multi-tenant enterprise memory system**
- neutral, immutable, configurable
- suitable for many industries without redesign
- extensible without fragmentation

This makes it a **long-term product**, not a single-company tool.

---

## 17. Technology Stack (Reference Implementation)

**Backend**:
- Python 3.11+ with FastAPI
- PostgreSQL 15+ (with RLS, JSONB, partitioning)
- Pydantic for validation
- SQLAlchemy / asyncpg for database
- Redis for caching

**Frontend** (optional):
- React 18+ with TypeScript
- Ant Design or similar UI library
- TanStack Query for data fetching

**Storage**:
- S3 / MinIO / Azure Blob for documents
- PostgreSQL for all structured data

**Deployment**:
- Docker containers
- Kubernetes or ECS/Fargate
- Managed PostgreSQL (RDS, Azure Database)
- Managed Redis (ElastiCache, Azure Cache)

---

## 18. Next Steps

To implement Timeline:

1. **Database Setup**
   - Create core tables (tenant, subject, event, document)
   - Implement RLS policies
   - Set up event hashing triggers

2. **API Layer**
   - FastAPI application structure
   - Tenant middleware
   - Event creation endpoint with validation
   - Timeline query endpoint

3. **Configuration System**
   - Schema registry tables
   - Subject/event type management
   - Validation engine

4. **Event Integrity**
   - Hash calculation functions
   - Chain verification API
   - Periodic integrity checks

5. **Frontend**
   - Timeline visualization component
   - Subject management UI
   - Event creation forms
   - Document viewer

6. **Testing**
   - Unit tests for event hashing
   - Integration tests for multi-tenancy
   - Security tests for tenant isolation
   - Performance tests for timeline queries

---

**Timeline is ready to be built.**

All architectural decisions are made.
The core model is industry-agnostic.
The path to production is clear.
