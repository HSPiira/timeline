# Timeline – Multi-Tenant Enterprise Memory System
## Technical Specification Document

**Version:** 2.0
**Date:** December 13, 2024
**Status:** Production Specification
**Product:** Timeline - System of Record for Enterprise History

---

## Executive Summary

### Vision Statement

**Timeline is a multi-tenant enterprise memory system** that captures what happened, to whom, when, by whom, and with what evidence — immutably and traceably.

Timeline is:
- **Industry-agnostic** at its core
- **Multi-tenant** by design
- **Configurable** rather than hard-coded
- **Immutable** with cryptographic event chaining
- Suitable for **regulated, privacy-sensitive** organizations

### Core Philosophy

Timeline does **not** model full business logic of every industry. Instead, it models **facts and events** emitted by business processes.

Industries differ in *meaning*, not in *facts*:
- Facts are **events**
- Evidence is **documents**
- Ownership is **tenancy**
- History is **immutable**

Timeline records truth. Business interpretation sits above it.

### Target Markets

- **Insurance**: Policy lifecycles, claims, client relationships
- **Healthcare**: Patient histories, treatment records, provider networks
- **Finance**: Transaction histories, compliance trails, client onboarding
- **Procurement**: Supplier relationships, contract management, purchasing
- **Legal**: Case management, document chains, client matters
- **HR**: Employee lifecycles, compliance documentation

### Business Value

**For Organizations**:
- Single source of truth for organizational history
- Instant access to complete relationship timelines
- Automated compliance and audit trails
- 60-80% reduction in data retrieval time
- Immutable records for regulatory compliance

**For Timeline (SaaS Business)**:
- Recurring revenue model (per-tenant subscription)
- Multi-industry applicability
- High retention due to data gravity
- Network effects through integrations

### Technology Approach

**Architecture**: Multi-tenant SaaS with logical data isolation
**Backend**: Node.js + TypeScript + Express
**Database**: PostgreSQL 15+ with row-level security
**Event Store**: Immutable event ledger with cryptographic chaining
**Storage**: AWS S3 / Azure Blob (tenant-scoped)
**Frontend**: React + TypeScript (tenant-branded)
**Deployment**: Kubernetes on AWS/Azure/GCP

### Project Scope

**Phase 1** (Months 1-4): Core Platform - Multi-tenancy, subjects, events, documents
**Phase 2** (Months 5-8): Configuration Layer - Schema management, workflows, integrations
**Phase 3** (Months 9-12): SaaS Features - Billing, analytics, APIs, marketplace

**Budget**: $200K-$350K for MVP (2-3 developers × 12 months)
**Infrastructure**: $2K-$10K/month (scales with tenant count)

---

## Table of Contents

1. [Core Concepts](#1-core-concepts)
2. [Multi-Tenancy Architecture](#2-multi-tenancy-architecture)
3. [Canonical Data Model](#3-canonical-data-model)
4. [Database Design](#4-database-design)
5. [Event Sourcing & Immutability](#5-event-sourcing--immutability)
6. [Configuration Layer](#6-configuration-layer)
7. [API Specifications](#7-api-specifications)
8. [Frontend Application](#8-frontend-application)
9. [Security & Compliance](#9-security--compliance)
10. [Infrastructure & Deployment](#10-infrastructure--deployment)
11. [Implementation Roadmap](#11-implementation-roadmap)
12. [Development Guidelines](#12-development-guidelines)

---

## 1. Core Concepts

### 1.1 What is Timeline?

Timeline is a **system of record for enterprise history** that captures:
- **What happened**: Immutable events
- **To whom**: Subjects (clients, employees, assets, etc.)
- **When**: Precise timestamps
- **By whom**: Actors (users, systems)
- **With what evidence**: Documents and artifacts

### 1.2 Core Entities

#### Tenant
An organization using Timeline. Each tenant:
- Owns its data exclusively
- Defines its own subjects, events, and workflows
- Has isolated access control
- Cannot see other tenants' data

#### Subject
**Anything that can have a history**. Examples:
- Client, Supplier, Employee (people/orgs)
- Policy, Contract, Asset (things)
- Claim, Case, Project (processes)

Subjects are:
- Tenant-scoped
- Type-driven (configurable)
- The "who/what" of events

#### Event
An **immutable fact** about what happened. Events are:
- Timestamped precisely
- Cryptographically chained
- Never modified or deleted
- Industry-neutral in structure
- Semantically rich in payload

#### Document
Versioned, linked artifacts that provide evidence:
- Uploaded files (PDFs, images, spreadsheets)
- Generated documents (reports, invoices)
- Emails and correspondence
- Scanned documents

Documents are:
- Tenant-scoped
- Immutable and versioned
- Linked to events and/or subjects

### 1.3 Design Principles

1. **Immutability**: Events are write-once, never modified
2. **Tenant Isolation**: Complete data segregation between organizations
3. **Configuration Over Code**: Business logic via configuration, not hard-coding
4. **Industry Neutrality**: Core model works for any industry
5. **Evidence-Based**: Every claim backed by documents
6. **Auditability**: Complete trail of who did what when
7. **Scalability**: From 1 tenant to 10,000+ tenants

### 1.4 What Timeline Is NOT

- ❌ Not a full ERP or CRM system
- ❌ Not an industry-specific application
- ❌ Not a transaction processing system
- ❌ Not a real-time operational database

Timeline **records what happened** in other systems. It's the organizational memory layer.

---

## 2. Multi-Tenancy Architecture

### 2.1 Tenant = Organization

Every organization using Timeline is a **tenant**.

**Tenant Characteristics**:
```yaml
tenant:
  id: UUID
  name: "Acme Insurance Co."
  slug: "acme-insurance"
  industry: "insurance"  # label only, not logic
  tier: "enterprise"      # pricing tier
  status: "active"
  created_at: timestamp
  configuration:
    subject_types: [...]
    event_types: [...]
    workflows: [...]
    branding: {...}
```

### 2.2 Isolation Model

**Logical Isolation with Hard Guards** (recommended approach):

```
┌─────────────────────────────────────────────────────────┐
│                  Single PostgreSQL Database              │
├─────────────────────────────────────────────────────────┤
│  Table: subjects                                         │
│  ┌──────────────┬──────────┬──────────┬──────────┐     │
│  │ id           │tenant_id │ type     │ data     │     │
│  ├──────────────┼──────────┼──────────┼──────────┤     │
│  │ subj-1       │ TENANT-A │ CLIENT   │ {...}    │     │
│  │ subj-2       │ TENANT-A │ POLICY   │ {...}    │     │
│  │ subj-3       │ TENANT-B │ CLIENT   │ {...}    │     │
│  │ subj-4       │ TENANT-B │ EMPLOYEE │ {...}    │     │
│  └──────────────┴──────────┴──────────┴──────────┘     │
│                                                          │
│  Row-Level Security Policies:                           │
│  - WHERE tenant_id = current_tenant_id()                │
│  - Enforced at database level                           │
└─────────────────────────────────────────────────────────┘
```

**Isolation Guarantees**:
- `tenant_id` on **all** core tables
- Row-level security (RLS) enforced at DB level
- Tenant-scoped encryption keys
- Tenant-aware caching (Redis namespaces: `tenant:{id}:*`)
- API-level tenant context validation

**Benefits**:
- Lower operational cost (single DB cluster)
- Easier onboarding of new tenants
- Simplified backups and maintenance
- Strong security guarantees via RLS

**Physical Isolation Option**:
Available for high-risk/high-value clients:
- Separate database per tenant
- Dedicated infrastructure
- Custom compliance requirements

### 2.3 Tenant Context Resolution

**How tenant context is determined**:

```typescript
// Option 1: JWT Token Claims
{
  "user_id": "user-123",
  "tenant_id": "tenant-abc",
  "role": "manager",
  "permissions": [...]
}

// Option 2: Request Headers
X-Tenant-ID: tenant-abc

// Option 3: Subdomain Resolution
acme-insurance.timeline.app → tenant_slug = "acme-insurance"
```

**Enforcement at Every Layer**:
```
Request → API Gateway → Tenant Middleware → RLS → Response
            ↓              ↓                   ↓
         Validate    Set tenant_id     Database enforces
         JWT token   in context        WHERE tenant_id = X
```

### 2.4 Data Isolation Strategy

```sql
-- Set tenant context for session
SET app.current_tenant_id = 'tenant-abc';

-- Row-Level Security Policy
CREATE POLICY tenant_isolation ON subjects
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- All queries automatically filtered
SELECT * FROM subjects;  -- Only returns this tenant's subjects
```

### 2.5 Tenant Lifecycle

```yaml
onboarding:
  1. Create tenant record
  2. Initialize default configuration (subject types, event types)
  3. Create admin user
  4. Set up tenant-scoped resources (S3 bucket prefix, Redis namespace)
  5. Apply RLS policies
  6. Send welcome email + setup guide

offboarding:
  1. Mark tenant as suspended (soft delete)
  2. Export all data (compliance requirement)
  3. Archive documents to cold storage
  4. Anonymize data after retention period
  5. Final purge (if requested and legally allowed)
```

---

## 3. Canonical Data Model

### 3.1 Subject (The "Who / What")

A subject is **anything that can have a history**.

**Core Structure**:
```typescript
interface Subject {
  id: string;              // UUID
  tenant_id: string;       // Foreign key to tenant
  subject_type: string;    // Configured by tenant (e.g., "CLIENT", "POLICY")
  subject_code: string;    // Human-readable ID (e.g., "CLIENT-12345")
  display_name: string;    // Primary label

  // Flexible data storage
  attributes: Record<string, any>;  // JSON, validated against schema

  // Metadata
  created_at: Date;
  created_by: string;      // User ID
  updated_at: Date;
  deleted_at?: Date;       // Soft delete

  // Search
  search_vector: string;   // Full-text search (tsvector)
}
```

**Examples Across Industries**:

```yaml
# Insurance
subject_types:
  - CLIENT: {name, email, policy_count, total_premium}
  - POLICY: {policy_number, coverage_amount, start_date, end_date}
  - CLAIM: {claim_number, amount, status}

# Healthcare
subject_types:
  - PATIENT: {mrn, name, dob, primary_physician}
  - PROVIDER: {npi, name, specialty, network}
  - EPISODE: {episode_id, diagnosis, admission_date}

# Finance
subject_types:
  - ACCOUNT: {account_number, type, balance, owner}
  - TRANSACTION: {transaction_id, amount, counterparty}
  - LOAN: {loan_id, principal, interest_rate, term}
```

### 3.2 Event (The "What Happened")

An event is an **immutable fact** with cryptographic integrity.

**Core Structure**:
```typescript
interface Event {
  id: string;              // UUID
  tenant_id: string;

  // Subject reference
  subject_id: string;
  subject_type: string;    // Denormalized for performance

  // Event classification
  event_type: string;      // Configured by tenant (e.g., "PAYMENT_RECEIVED")
  event_category?: string; // Optional grouping

  // Temporal
  timestamp: Date;         // When it happened (can be historical)
  recorded_at: Date;       // When it was recorded in Timeline

  // Actor
  actor_type: 'user' | 'system' | 'external';
  actor_id: string;
  actor_name: string;      // Denormalized for auditability

  // Payload (industry-specific data)
  payload: Record<string, any>;  // Validated against schema

  // Immutability guarantees
  hash: string;            // SHA-256 hash of event content
  previous_hash: string;   // Hash of previous event (blockchain-style)
  signature?: string;      // Optional cryptographic signature

  // Metadata
  sequence_number: number; // Per-subject ordering
  version: number;         // Schema version
  tags: string[];

  // Never modified, never deleted
  readonly: true;
}
```

**Event Chaining (Immutability)**:
```
Event 1: hash = H(event_1_data)
         previous_hash = null

Event 2: hash = H(event_2_data)
         previous_hash = H(event_1_data)

Event 3: hash = H(event_3_data)
         previous_hash = H(event_2_data)

→ Any tampering breaks the chain
→ Cryptographically verifiable history
```

**Example Events**:

```yaml
# Insurance: Payment Received
event:
  event_type: "PAYMENT_RECEIVED"
  timestamp: "2024-12-01T10:30:00Z"
  subject_id: "policy-123"
  actor: "payment-gateway"
  payload:
    amount: 5000.00
    currency: "USD"
    invoice_id: "INV-2024-001"
    payment_method: "credit_card"
    transaction_id: "txn-abc123"

# Healthcare: Medication Prescribed
event:
  event_type: "MEDICATION_PRESCRIBED"
  timestamp: "2024-12-01T14:15:00Z"
  subject_id: "patient-456"
  actor_type: "user"
  actor_id: "dr-smith"
  payload:
    medication: "Amoxicillin"
    dosage: "500mg"
    frequency: "3x daily"
    duration_days: 10
    prescribing_npi: "1234567890"
```

### 3.3 Document (The Evidence)

Documents are versioned, immutable artifacts.

**Core Structure**:
```typescript
interface Document {
  id: string;
  tenant_id: string;

  // Links to subjects and/or events
  subject_ids: string[];   // Can belong to multiple subjects
  event_ids: string[];     // Can be evidence for multiple events

  // Classification
  document_category: string;  // Configured by tenant
  document_type?: string;     // More specific classification

  // File metadata
  filename: string;
  original_filename: string;
  file_extension: string;
  mime_type: string;
  file_size: number;
  checksum: string;        // SHA-256 for integrity

  // Storage
  storage_provider: 'aws_s3' | 'azure_blob' | 'gcp_storage';
  storage_path: string;    // tenants/{tenant_id}/documents/{year}/{id}
  storage_bucket: string;

  // Content
  title: string;
  description?: string;
  extracted_text?: string; // OCR/text extraction for search
  metadata: Record<string, any>;

  // Versioning
  version: number;
  parent_document_id?: string;
  is_latest_version: boolean;

  // Lifecycle
  document_date?: Date;    // Effective date
  expiry_date?: Date;
  retention_until?: Date;  // Compliance-driven retention

  // Access control
  access_level: 'public' | 'internal' | 'restricted' | 'confidential';

  // Audit
  uploaded_by: string;
  uploaded_at: Date;
  verified_by?: string;
  verified_at?: Date;

  // Soft delete (for compliance)
  deleted_at?: Date;
  deletion_reason?: string;
}
```

### 3.4 Tenant Configuration

Each tenant defines its own types and schemas.

**Subject Type Configuration**:
```typescript
interface SubjectTypeConfig {
  tenant_id: string;
  type_name: string;       // e.g., "CLIENT", "POLICY"
  display_name: string;    // e.g., "Client", "Insurance Policy"
  icon?: string;
  color?: string;

  // Schema definition
  schema: {
    type: "object",
    properties: {
      name: { type: "string", required: true },
      email: { type: "string", format: "email" },
      tier: { type: "string", enum: ["bronze", "silver", "gold"] }
      // ... using JSON Schema format
    }
  };

  // Behavior
  has_timeline: boolean;   // Default: true
  allow_documents: boolean; // Default: true

  created_at: Date;
  version: number;
}
```

**Event Type Configuration**:
```typescript
interface EventTypeConfig {
  tenant_id: string;
  event_type: string;      // e.g., "PAYMENT_RECEIVED"
  display_name: string;
  category?: string;
  icon?: string;
  color?: string;

  // Payload schema
  payload_schema: {
    type: "object",
    properties: {
      amount: { type: "number", minimum: 0 },
      currency: { type: "string", enum: ["USD", "EUR", "GBP"] }
      // ... using JSON Schema format
    }
  };

  // Behavior
  is_milestone: boolean;
  importance: 'low' | 'normal' | 'high' | 'critical';

  // Automation
  triggers_workflow?: string; // Workflow ID to execute
  requires_approval?: boolean;

  created_at: Date;
  version: number;
}
```

---

## 4. Database Design

### 4.1 Schema Overview

**Design Principles**:
- Multi-tenant with `tenant_id` on all tables
- Row-level security (RLS) enforcement
- Event immutability (append-only events table)
- Cryptographic chaining for events
- Flexible JSON schemas for tenant-specific data
- Partitioning for timeline scalability

### 4.2 Core Tables

#### 4.2.1 Tenants Table

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Identity
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,  -- URL-safe identifier

    -- Classification
    industry VARCHAR(100),  -- informational only

    -- Subscription
    tier VARCHAR(50) DEFAULT 'starter',  -- starter, professional, enterprise
    status VARCHAR(50) DEFAULT 'active',  -- active, suspended, cancelled

    -- Limits
    max_users INTEGER DEFAULT 10,
    max_subjects INTEGER,  -- null = unlimited
    max_storage_gb INTEGER DEFAULT 100,

    -- Configuration (JSON)
    config JSONB DEFAULT '{}',
    branding JSONB DEFAULT '{}',  -- logo, colors, etc.

    -- Billing
    stripe_customer_id VARCHAR(255),
    subscription_id VARCHAR(255),

    -- Dates
    trial_ends_at TIMESTAMPTZ,
    subscribed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_tenants_slug ON tenants(slug) WHERE deleted_at IS NULL;
CREATE INDEX idx_tenants_status ON tenants(status) WHERE deleted_at IS NULL;
```

#### 4.2.2 Subjects Table

```sql
CREATE TABLE subjects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Multi-tenancy
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Type (configured by tenant)
    subject_type VARCHAR(100) NOT NULL,
    subject_code VARCHAR(100) NOT NULL,  -- Human-readable ID

    -- Display
    display_name VARCHAR(500) NOT NULL,

    -- Flexible attributes (validated against tenant's schema)
    attributes JSONB DEFAULT '{}',

    -- Search
    search_vector tsvector,
    tags TEXT[],

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID,  -- References users table
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID,
    deleted_at TIMESTAMPTZ,

    -- Constraints
    CONSTRAINT unique_subject_code_per_tenant UNIQUE (tenant_id, subject_code),
    CONSTRAINT unique_subject_name_per_type UNIQUE (tenant_id, subject_type, display_name)
);

-- Indexes
CREATE INDEX idx_subjects_tenant ON subjects(tenant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_subjects_type ON subjects(tenant_id, subject_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_subjects_code ON subjects(subject_code);
CREATE INDEX idx_subjects_search ON subjects USING GIN(search_vector);
CREATE INDEX idx_subjects_tags ON subjects USING GIN(tags);
CREATE INDEX idx_subjects_attributes ON subjects USING GIN(attributes);

-- Row-Level Security
ALTER TABLE subjects ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_subjects ON subjects
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Search vector trigger
CREATE TRIGGER subjects_search_update
    BEFORE INSERT OR UPDATE ON subjects
    FOR EACH ROW EXECUTE FUNCTION
    tsvector_update_trigger(search_vector, 'pg_catalog.english',
        display_name, subject_code);
```

#### 4.2.3 Events Table (Immutable, Partitioned)

```sql
-- Event chain tracking per subject
CREATE TABLE event_chains (
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    subject_id UUID NOT NULL REFERENCES subjects(id),
    last_event_hash VARCHAR(64),
    event_count BIGINT DEFAULT 0,
    last_event_at TIMESTAMPTZ,

    PRIMARY KEY (tenant_id, subject_id)
);

-- Main events table (partitioned by tenant and date)
CREATE TABLE events (
    id UUID DEFAULT uuid_generate_v4(),

    -- Multi-tenancy
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Subject reference
    subject_id UUID NOT NULL,
    subject_type VARCHAR(100) NOT NULL,  -- Denormalized

    -- Event classification
    event_type VARCHAR(100) NOT NULL,
    event_category VARCHAR(100),

    -- Temporal
    timestamp TIMESTAMPTZ NOT NULL,  -- When it happened
    recorded_at TIMESTAMPTZ DEFAULT NOW(),  -- When recorded
    event_date DATE GENERATED ALWAYS AS (timestamp::DATE) STORED,

    -- Actor
    actor_type VARCHAR(50) NOT NULL,  -- 'user', 'system', 'external'
    actor_id VARCHAR(255),
    actor_name VARCHAR(255),

    -- Payload (validated against event type schema)
    payload JSONB DEFAULT '{}',

    -- Immutability & Integrity
    hash VARCHAR(64) NOT NULL,  -- SHA-256 of event content
    previous_hash VARCHAR(64),  -- Previous event hash (blockchain-style)
    signature VARCHAR(512),     -- Optional cryptographic signature

    -- Ordering
    sequence_number BIGINT NOT NULL,  -- Per-subject sequence

    -- Metadata
    version INTEGER DEFAULT 1,  -- Schema version
    tags TEXT[],
    importance VARCHAR(20) DEFAULT 'normal',
    is_milestone BOOLEAN DEFAULT false,

    -- Search
    search_vector tsvector,

    -- Events are NEVER modified or deleted
    readonly BOOLEAN DEFAULT true,

    -- Audit (creation only)
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Partition key
    PRIMARY KEY (id, tenant_id, event_date),

    -- Foreign key
    FOREIGN KEY (tenant_id, subject_id) REFERENCES subjects(tenant_id, id),

    -- Constraints
    CONSTRAINT valid_hash_format CHECK (hash ~ '^[a-f0-9]{64}$'),
    CONSTRAINT valid_previous_hash CHECK (previous_hash IS NULL OR previous_hash ~ '^[a-f0-9]{64}$')

) PARTITION BY LIST (tenant_id);

-- Create partitions dynamically per tenant (example for 3 tenants)
-- In production, created automatically when tenant onboards

-- Indexes (applied to partitioned table)
CREATE INDEX idx_events_subject ON events(subject_id, timestamp DESC);
CREATE INDEX idx_events_type ON events(event_type, timestamp DESC);
CREATE INDEX idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX idx_events_actor ON events(actor_id, timestamp DESC);
CREATE INDEX idx_events_hash ON events(hash);
CREATE INDEX idx_events_search ON events USING GIN(search_vector);
CREATE INDEX idx_events_payload ON events USING GIN(payload);

-- Row-Level Security
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_events ON events
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Prevent updates/deletes on events (immutability)
CREATE POLICY events_immutable ON events
    FOR UPDATE
    USING (false);

CREATE POLICY events_no_delete ON events
    FOR DELETE
    USING (false);

-- Search vector trigger
CREATE TRIGGER events_search_update
    BEFORE INSERT ON events
    FOR EACH ROW EXECUTE FUNCTION
    tsvector_update_trigger(search_vector, 'pg_catalog.english',
        event_type, actor_name);
```

**Event Hash Calculation**:
```sql
CREATE OR REPLACE FUNCTION calculate_event_hash(
    p_tenant_id UUID,
    p_subject_id UUID,
    p_event_type VARCHAR,
    p_timestamp TIMESTAMPTZ,
    p_payload JSONB
) RETURNS VARCHAR AS $$
DECLARE
    content TEXT;
BEGIN
    content := p_tenant_id::TEXT || '|' ||
               p_subject_id::TEXT || '|' ||
               p_event_type || '|' ||
               p_timestamp::TEXT || '|' ||
               p_payload::TEXT;

    RETURN encode(digest(content, 'sha256'), 'hex');
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

**Event Chaining Trigger**:
```sql
CREATE OR REPLACE FUNCTION maintain_event_chain()
RETURNS TRIGGER AS $$
DECLARE
    last_hash VARCHAR(64);
    next_sequence BIGINT;
BEGIN
    -- Get last event hash and next sequence number
    SELECT
        last_event_hash,
        event_count + 1
    INTO
        last_hash,
        next_sequence
    FROM event_chains
    WHERE tenant_id = NEW.tenant_id
      AND subject_id = NEW.subject_id
    FOR UPDATE;

    -- If no chain exists, create it
    IF NOT FOUND THEN
        INSERT INTO event_chains (tenant_id, subject_id, last_event_hash, event_count, last_event_at)
        VALUES (NEW.tenant_id, NEW.subject_id, NULL, 0, NOW());

        last_hash := NULL;
        next_sequence := 1;
    END IF;

    -- Set sequence and previous hash
    NEW.sequence_number := next_sequence;
    NEW.previous_hash := last_hash;

    -- Calculate hash for this event
    NEW.hash := calculate_event_hash(
        NEW.tenant_id,
        NEW.subject_id,
        NEW.event_type,
        NEW.timestamp,
        NEW.payload
    );

    -- Update chain
    UPDATE event_chains
    SET last_event_hash = NEW.hash,
        event_count = next_sequence,
        last_event_at = NEW.timestamp
    WHERE tenant_id = NEW.tenant_id
      AND subject_id = NEW.subject_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER maintain_event_chain_trigger
    BEFORE INSERT ON events
    FOR EACH ROW
    EXECUTE FUNCTION maintain_event_chain();
```

#### 4.2.4 Documents Table

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Multi-tenancy
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Classification
    document_category VARCHAR(100) NOT NULL,
    document_type VARCHAR(100),

    -- File metadata
    filename VARCHAR(500) NOT NULL,
    original_filename VARCHAR(500),
    file_extension VARCHAR(10),
    mime_type VARCHAR(100),
    file_size BIGINT,
    checksum VARCHAR(64),  -- SHA-256

    -- Storage
    storage_provider VARCHAR(50) DEFAULT 'aws_s3',
    storage_path TEXT NOT NULL,
    storage_bucket VARCHAR(255),

    -- Content
    title VARCHAR(500),
    description TEXT,
    extracted_text TEXT,  -- OCR/extraction for search
    metadata JSONB DEFAULT '{}',

    -- Versioning
    version INTEGER DEFAULT 1,
    parent_document_id UUID REFERENCES documents(id),
    is_latest_version BOOLEAN DEFAULT true,

    -- Lifecycle
    document_date DATE,
    expiry_date DATE,
    retention_until DATE,

    -- Access control
    access_level VARCHAR(50) DEFAULT 'internal',

    -- Search
    search_vector tsvector,
    tags TEXT[],

    -- Audit
    uploaded_by UUID,
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    verified_by UUID,
    verified_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    deletion_reason TEXT,

    CONSTRAINT positive_file_size CHECK (file_size > 0)
);

-- Indexes
CREATE INDEX idx_documents_tenant ON documents(tenant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_documents_category ON documents(document_category) WHERE deleted_at IS NULL;
CREATE INDEX idx_documents_search ON documents USING GIN(search_vector);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);
CREATE INDEX idx_documents_expiry ON documents(expiry_date)
    WHERE expiry_date IS NOT NULL AND deleted_at IS NULL;

-- Row-Level Security
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_documents ON documents
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Junction tables for many-to-many relationships
CREATE TABLE subject_documents (
    subject_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,  -- For RLS
    relationship_type VARCHAR(100),  -- e.g., 'contract', 'kyc', 'correspondence'
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (subject_id, document_id),
    FOREIGN KEY (tenant_id, subject_id) REFERENCES subjects(tenant_id, id)
);

CREATE INDEX idx_subject_documents_subject ON subject_documents(subject_id);
CREATE INDEX idx_subject_documents_document ON subject_documents(document_id);

ALTER TABLE subject_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_subject_documents ON subject_documents
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

CREATE TABLE event_documents (
    event_id UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,  -- For RLS
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (event_id, document_id)
);

CREATE INDEX idx_event_documents_event ON event_documents(event_id);
CREATE INDEX idx_event_documents_document ON event_documents(document_id);

ALTER TABLE event_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_event_documents ON event_documents
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

#### 4.2.5 Configuration Tables

```sql
-- Subject type definitions per tenant
CREATE TABLE subject_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    type_name VARCHAR(100) NOT NULL,  -- e.g., "CLIENT", "POLICY"
    display_name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Visual
    icon VARCHAR(100),
    color VARCHAR(50),

    -- Schema (JSON Schema format)
    schema JSONB NOT NULL,

    -- Behavior
    has_timeline BOOLEAN DEFAULT true,
    allow_documents BOOLEAN DEFAULT true,

    -- Versioning
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID,
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_type_per_tenant UNIQUE (tenant_id, type_name)
);

CREATE INDEX idx_subject_types_tenant ON subject_types(tenant_id) WHERE is_active = true;

ALTER TABLE subject_types ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_subject_types ON subject_types
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Event type definitions per tenant
CREATE TABLE event_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,  -- e.g., "PAYMENT_RECEIVED"
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),

    -- Visual
    icon VARCHAR(100),
    color VARCHAR(50),

    -- Payload schema (JSON Schema format)
    payload_schema JSONB NOT NULL,

    -- Behavior
    is_milestone BOOLEAN DEFAULT false,
    importance VARCHAR(20) DEFAULT 'normal',
    requires_approval BOOLEAN DEFAULT false,

    -- Automation
    triggers_workflow UUID,  -- References workflows table

    -- Versioning
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID,
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_event_type_per_tenant UNIQUE (tenant_id, event_type)
);

CREATE INDEX idx_event_types_tenant ON event_types(tenant_id) WHERE is_active = true;
CREATE INDEX idx_event_types_category ON event_types(tenant_id, category);

ALTER TABLE event_types ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_event_types ON event_types
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Document category definitions per tenant
CREATE TABLE document_categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    category_name VARCHAR(100) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Metadata schema
    metadata_schema JSONB,

    -- Retention
    default_retention_days INTEGER,

    -- Versioning
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_category_per_tenant UNIQUE (tenant_id, category_name)
);

ALTER TABLE document_categories ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_document_categories ON document_categories
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

#### 4.2.6 Users & Authentication

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Multi-tenancy (users belong to one tenant)
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Authentication
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,

    -- Profile
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    display_name VARCHAR(255),
    avatar_url TEXT,

    -- Authorization
    role VARCHAR(50) DEFAULT 'viewer',  -- admin, manager, agent, viewer
    permissions JSONB DEFAULT '{}',

    -- Status
    status VARCHAR(50) DEFAULT 'active',  -- active, suspended, invited
    email_verified BOOLEAN DEFAULT false,

    -- Security
    mfa_enabled BOOLEAN DEFAULT false,
    mfa_secret VARCHAR(255),
    last_login_at TIMESTAMPTZ,
    last_login_ip INET,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,

    CONSTRAINT unique_email_per_tenant UNIQUE (tenant_id, email)
);

CREATE INDEX idx_users_tenant ON users(tenant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_email ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role ON users(tenant_id, role) WHERE deleted_at IS NULL;

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_users ON users
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Audit log (immutable)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    -- Action
    user_id UUID,
    action VARCHAR(100) NOT NULL,  -- 'create', 'read', 'update', 'delete'
    resource_type VARCHAR(100) NOT NULL,
    resource_id UUID,

    -- Context
    ip_address INET,
    user_agent TEXT,
    request_id VARCHAR(100),

    -- Changes
    old_values JSONB,
    new_values JSONB,

    -- Metadata
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT true,
    error_message TEXT,

    -- Immutable
    readonly BOOLEAN DEFAULT true
);

CREATE INDEX idx_audit_logs_tenant ON audit_logs(tenant_id, timestamp DESC);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id, timestamp DESC);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_audit_logs ON audit_logs
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

#### 4.2.7 Workflows (Declarative)

```sql
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Trigger
    trigger_event_type VARCHAR(100),  -- Which event type triggers this
    trigger_conditions JSONB,  -- Conditions on event payload

    -- Actions (declarative)
    actions JSONB NOT NULL,
    -- Example: [
    --   {type: "emit_event", event_type: "APPROVAL_REQUIRED", payload_template: {...}},
    --   {type: "notify", role: "manager", template: "approval_needed"},
    --   {type: "create_task", assigned_to_role: "agent"}
    -- ]

    -- Status
    is_active BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID,
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_workflow_name UNIQUE (tenant_id, name)
);

CREATE INDEX idx_workflows_tenant ON workflows(tenant_id) WHERE is_active = true;
CREATE INDEX idx_workflows_trigger ON workflows(trigger_event_type) WHERE is_active = true;

ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_workflows ON workflows
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Workflow executions log
CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),

    workflow_id UUID NOT NULL REFERENCES workflows(id),
    trigger_event_id UUID,  -- Which event triggered it

    status VARCHAR(50) DEFAULT 'completed',  -- completed, failed

    actions_taken JSONB,  -- What actions were executed
    error_message TEXT,

    executed_at TIMESTAMPTZ DEFAULT NOW(),
    duration_ms INTEGER
);

CREATE INDEX idx_workflow_executions_tenant ON workflow_executions(tenant_id, executed_at DESC);
CREATE INDEX idx_workflow_executions_workflow ON workflow_executions(workflow_id);

ALTER TABLE workflow_executions ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_workflow_executions ON workflow_executions
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

### 4.3 Database Functions

```sql
-- Function to set tenant context
CREATE OR REPLACE FUNCTION set_tenant_context(p_tenant_id UUID)
RETURNS void AS $$
BEGIN
    PERFORM set_config('app.current_tenant_id', p_tenant_id::text, false);
END;
$$ LANGUAGE plpgsql;

-- Function to get current tenant
CREATE OR REPLACE FUNCTION current_tenant_id()
RETURNS UUID AS $$
BEGIN
    RETURN current_setting('app.current_tenant_id', true)::uuid;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_subjects_updated_at BEFORE UPDATE ON subjects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Event integrity verification
CREATE OR REPLACE FUNCTION verify_event_chain(
    p_tenant_id UUID,
    p_subject_id UUID
) RETURNS BOOLEAN AS $$
DECLARE
    event_rec RECORD;
    expected_hash VARCHAR(64);
    prev_hash VARCHAR(64) := NULL;
BEGIN
    FOR event_rec IN
        SELECT hash, previous_hash, tenant_id, subject_id, event_type, timestamp, payload
        FROM events
        WHERE tenant_id = p_tenant_id
          AND subject_id = p_subject_id
        ORDER BY sequence_number
    LOOP
        -- Verify previous hash matches
        IF event_rec.previous_hash IS DISTINCT FROM prev_hash THEN
            RETURN false;
        END IF;

        -- Recalculate hash and verify
        expected_hash := calculate_event_hash(
            event_rec.tenant_id,
            event_rec.subject_id,
            event_rec.event_type,
            event_rec.timestamp,
            event_rec.payload
        );

        IF event_rec.hash != expected_hash THEN
            RETURN false;
        END IF;

        prev_hash := event_rec.hash;
    END LOOP;

    RETURN true;
END;
$$ LANGUAGE plpgsql;
```

### 4.4 Seed Data (Default Configurations)

```sql
-- Default subject types for insurance tenant
CREATE OR REPLACE FUNCTION seed_insurance_config(p_tenant_id UUID)
RETURNS void AS $$
BEGIN
    -- Subject Types
    INSERT INTO subject_types (tenant_id, type_name, display_name, schema) VALUES
    (p_tenant_id, 'CLIENT', 'Client', '{
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string", "format": "email"},
            "phone": {"type": "string"},
            "tier": {"type": "string", "enum": ["bronze", "silver", "gold"]}
        },
        "required": ["name"]
    }'::jsonb),
    (p_tenant_id, 'POLICY', 'Insurance Policy', '{
        "type": "object",
        "properties": {
            "policy_number": {"type": "string"},
            "coverage_amount": {"type": "number", "minimum": 0},
            "premium": {"type": "number", "minimum": 0},
            "start_date": {"type": "string", "format": "date"},
            "end_date": {"type": "string", "format": "date"}
        },
        "required": ["policy_number", "coverage_amount"]
    }'::jsonb),
    (p_tenant_id, 'CLAIM', 'Insurance Claim', '{
        "type": "object",
        "properties": {
            "claim_number": {"type": "string"},
            "amount": {"type": "number", "minimum": 0},
            "status": {"type": "string", "enum": ["pending", "approved", "rejected"]},
            "incident_date": {"type": "string", "format": "date"}
        },
        "required": ["claim_number", "amount"]
    }'::jsonb);

    -- Event Types
    INSERT INTO event_types (tenant_id, event_type, display_name, payload_schema, is_milestone) VALUES
    (p_tenant_id, 'CLIENT_ONBOARDED', 'Client Onboarded', '{
        "type": "object",
        "properties": {
            "onboarding_channel": {"type": "string"},
            "assigned_agent": {"type": "string"}
        }
    }'::jsonb, true),
    (p_tenant_id, 'POLICY_CREATED', 'Policy Created', '{
        "type": "object",
        "properties": {
            "policy_number": {"type": "string"},
            "policy_type": {"type": "string"},
            "coverage_amount": {"type": "number"}
        }
    }'::jsonb, true),
    (p_tenant_id, 'PAYMENT_RECEIVED', 'Payment Received', '{
        "type": "object",
        "properties": {
            "amount": {"type": "number", "minimum": 0},
            "currency": {"type": "string"},
            "payment_method": {"type": "string"},
            "invoice_id": {"type": "string"}
        },
        "required": ["amount", "currency"]
    }'::jsonb, false),
    (p_tenant_id, 'CLAIM_SUBMITTED', 'Claim Submitted', '{
        "type": "object",
        "properties": {
            "claim_number": {"type": "string"},
            "claim_amount": {"type": "number"},
            "incident_description": {"type": "string"}
        }
    }'::jsonb, true);

    -- Document Categories
    INSERT INTO document_categories (tenant_id, category_name, display_name, default_retention_days) VALUES
    (p_tenant_id, 'CONTRACT', 'Contract', 2555),  -- 7 years
    (p_tenant_id, 'POLICY', 'Policy Document', 2555),
    (p_tenant_id, 'INVOICE', 'Invoice', 1825),  -- 5 years
    (p_tenant_id, 'CLAIM_FORM', 'Claim Form', 2555),
    (p_tenant_id, 'KYC', 'KYC Document', 1825);
END;
$$ LANGUAGE plpgsql;
```

---

## 5. Event Sourcing & Immutability

### 5.1 Event Sourcing Principles

**Timeline uses event sourcing for the event log**:

```
Traditional CRUD:
┌─────────────┐
│ UPDATE      │  ← State is overwritten, history lost
│ subjects    │
│ SET status  │
│ = 'active'  │
└─────────────┘

Event Sourcing:
┌─────────────┐
│ INSERT INTO │  ← New event appended, history preserved
│ events      │
│ (event_type │
│ = 'ACTIVATED')
└─────────────┘

Current state = Replay all events
```

**Benefits**:
- Complete audit trail
- Time travel (reconstruct state at any point)
- Event replay for debugging
- Compliance and legal requirements
- Never lose data

### 5.2 Cryptographic Event Chaining

**Each event contains**:
```typescript
{
  hash: SHA256(event_content),
  previous_hash: previous_event.hash
}
```

**Chain verification**:
```typescript
async function verifyEventChain(tenantId: string, subjectId: string): Promise<boolean> {
  const events = await getEvents(tenantId, subjectId); // Ordered by sequence

  let previousHash: string | null = null;

  for (const event of events) {
    // Check previous hash matches
    if (event.previous_hash !== previousHash) {
      console.error(`Chain broken at event ${event.id}`);
      return false;
    }

    // Recalculate hash and verify
    const expectedHash = calculateHash(event);
    if (event.hash !== expectedHash) {
      console.error(`Hash mismatch at event ${event.id}`);
      return false;
    }

    previousHash = event.hash;
  }

  return true;
}
```

**Tamper detection**:
- If anyone modifies an event, its hash changes
- This breaks the chain for all subsequent events
- Tampering is immediately detectable

### 5.3 Event Immutability Guarantees

**Database-level enforcement**:
```sql
-- Prevent updates
CREATE POLICY events_immutable ON events
    FOR UPDATE USING (false);

-- Prevent deletes
CREATE POLICY events_no_delete ON events
    FOR DELETE USING (false);

-- Readonly flag
readonly BOOLEAN DEFAULT true
```

**Application-level safeguards**:
```typescript
class EventRepository {
  async create(event: Event): Promise<Event> {
    // Only INSERT allowed
    return db.events.create(event);
  }

  async update(): Promise<never> {
    throw new Error('Events are immutable and cannot be updated');
  }

  async delete(): Promise<never> {
    throw new Error('Events are immutable and cannot be deleted');
  }
}
```

**Correction mechanism**:
If an event was recorded incorrectly, emit a **correction event**:
```typescript
// Original event (wrong amount)
{
  event_type: 'PAYMENT_RECEIVED',
  payload: { amount: 5000 }  // Should have been 6000
}

// Correction event
{
  event_type: 'PAYMENT_CORRECTED',
  payload: {
    corrects_event_id: 'event-123',
    original_amount: 5000,
    corrected_amount: 6000,
    reason: 'Data entry error'
  }
}
```

### 5.4 State Reconstruction

**Current state of a subject** = aggregate of all its events:

```typescript
async function getSubjectCurrentState(subjectId: string): Promise<SubjectState> {
  const events = await getEvents(subjectId);

  let state = {
    status: 'prospect',
    balance: 0,
    policies: []
  };

  for (const event of events) {
    state = applyEvent(state, event);
  }

  return state;
}

function applyEvent(state: SubjectState, event: Event): SubjectState {
  switch (event.event_type) {
    case 'CLIENT_ONBOARDED':
      return { ...state, status: 'active' };

    case 'PAYMENT_RECEIVED':
      return { ...state, balance: state.balance + event.payload.amount };

    case 'POLICY_CREATED':
      return { ...state, policies: [...state.policies, event.payload] };

    default:
      return state;
  }
}
```

**Snapshots for performance** (optional optimization):
```sql
CREATE TABLE subject_snapshots (
    subject_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    snapshot_at_event_id UUID NOT NULL,
    snapshot_at_sequence BIGINT NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Rebuild state = snapshot + events since snapshot
```

### 5.5 Time Travel Queries

**View state at any point in history**:

```typescript
async function getSubjectStateAt(
  subjectId: string,
  asOfDate: Date
): Promise<SubjectState> {
  const events = await db.events.findMany({
    where: {
      subject_id: subjectId,
      timestamp: { lte: asOfDate }
    },
    orderBy: { sequence_number: 'asc' }
  });

  return events.reduce(applyEvent, initialState);
}
```

**Example use cases**:
- "What was this client's status on January 1, 2023?"
- "How many active policies did we have last quarter?"
- "Reconstruct the state before this claim was filed"

---

## 6. Configuration Layer

### 6.1 Tenant-Owned Schema Definitions

Each tenant configures:
- **Subject types**: What entities they track (CLIENT, POLICY, EMPLOYEE, etc.)
- **Event types**: What events can occur (PAYMENT_RECEIVED, CLAIM_APPROVED, etc.)
- **Document categories**: How documents are classified

### 6.2 Subject Type Configuration

**UI Workflow**:
1. Admin navigates to Settings → Subject Types
2. Clicks "Add Subject Type"
3. Fills form:
   - Type name: `POLICY`
   - Display name: `Insurance Policy`
   - Schema definition (JSON Schema):
   ```json
   {
     "type": "object",
     "properties": {
       "policy_number": { "type": "string", "required": true },
       "coverage_amount": { "type": "number", "minimum": 0 },
       "premium": { "type": "number" },
       "start_date": { "type": "string", "format": "date" },
       "end_date": { "type": "string", "format": "date" }
     }
   }
   ```
4. System validates schema
5. Subject type is now available for use

**API Endpoint**:
```typescript
POST /api/v1/tenants/{tenant_id}/subject-types

{
  "type_name": "POLICY",
  "display_name": "Insurance Policy",
  "schema": {
    "type": "object",
    "properties": {...}
  },
  "icon": "document-text",
  "color": "#4CAF50"
}
```

**Validation on Subject Creation**:
```typescript
async function createSubject(data: CreateSubjectDTO) {
  const subjectType = await db.subjectTypes.findOne({
    where: { tenant_id: data.tenant_id, type_name: data.subject_type }
  });

  if (!subjectType) {
    throw new Error(`Subject type ${data.subject_type} not configured`);
  }

  // Validate attributes against schema
  const valid = validateJsonSchema(data.attributes, subjectType.schema);
  if (!valid) {
    throw new ValidationError('Attributes do not match schema');
  }

  return db.subjects.create(data);
}
```

### 6.3 Event Type Configuration

**Example Event Type Definition**:
```json
{
  "event_type": "PAYMENT_RECEIVED",
  "display_name": "Payment Received",
  "category": "financial",
  "payload_schema": {
    "type": "object",
    "properties": {
      "amount": { "type": "number", "minimum": 0, "required": true },
      "currency": { "type": "string", "enum": ["USD", "EUR", "GBP"], "required": true },
      "payment_method": { "type": "string" },
      "invoice_id": { "type": "string" },
      "transaction_id": { "type": "string" }
    }
  },
  "is_milestone": false,
  "importance": "normal",
  "triggers_workflow": null
}
```

**Schema Evolution**:
```typescript
// Version 1 of event type
{
  event_type: "PAYMENT_RECEIVED",
  version: 1,
  payload_schema: {
    properties: {
      amount: { type: "number" }
    }
  }
}

// Version 2 (added currency field)
{
  event_type: "PAYMENT_RECEIVED",
  version: 2,
  payload_schema: {
    properties: {
      amount: { type: "number" },
      currency: { type: "string", default: "USD" }  // Backward compatible
    }
  }
}

// Events store their schema version
event.version = 2
```

### 6.4 Document Category Configuration

**Example**:
```json
{
  "category_name": "CONTRACT",
  "display_name": "Contract",
  "metadata_schema": {
    "type": "object",
    "properties": {
      "contract_type": { "type": "string", "enum": ["service", "employment", "vendor"] },
      "effective_date": { "type": "string", "format": "date" },
      "expiry_date": { "type": "string", "format": "date" },
      "parties": { "type": "array", "items": { "type": "string" } }
    }
  },
  "default_retention_days": 2555  // 7 years
}
```

### 6.5 Workflow Configuration (Declarative)

**Example Workflow**:
```json
{
  "name": "High-Value Claim Approval",
  "trigger_event_type": "CLAIM_SUBMITTED",
  "trigger_conditions": {
    "payload.claim_amount": { ">": 10000 }
  },
  "actions": [
    {
      "type": "emit_event",
      "event_type": "APPROVAL_REQUIRED",
      "payload_template": {
        "claim_id": "{{trigger_event.payload.claim_number}}",
        "amount": "{{trigger_event.payload.claim_amount}}",
        "requester": "{{trigger_event.actor_name}}"
      }
    },
    {
      "type": "notify",
      "role": "manager",
      "template": "high_value_claim_submitted",
      "data": {
        "claim_number": "{{trigger_event.payload.claim_number}}",
        "amount": "{{trigger_event.payload.claim_amount}}"
      }
    },
    {
      "type": "create_task",
      "assigned_to_role": "claims_manager",
      "title": "Review high-value claim {{trigger_event.payload.claim_number}}",
      "due_in_hours": 24
    }
  ]
}
```

**Workflow Execution**:
```typescript
async function executeWorkflows(event: Event) {
  const workflows = await db.workflows.findMany({
    where: {
      tenant_id: event.tenant_id,
      is_active: true,
      trigger_event_type: event.event_type
    }
  });

  for (const workflow of workflows) {
    // Check conditions
    if (!evaluateConditions(workflow.trigger_conditions, event.payload)) {
      continue;
    }

    // Execute actions
    for (const action of workflow.actions) {
      await executeAction(action, event);
    }

    // Log execution
    await db.workflowExecutions.create({
      workflow_id: workflow.id,
      trigger_event_id: event.id,
      status: 'completed',
      actions_taken: workflow.actions
    });
  }
}
```

### 6.6 Configuration UI

**Settings Page Structure**:
```
Settings
├── Subject Types
│   ├── List of configured types
│   ├── Add new type
│   └── Edit type (versioned)
├── Event Types
│   ├── List by category
│   ├── Add new type
│   └── Configure workflows
├── Document Categories
│   ├── List of categories
│   ├── Retention policies
│   └── Access levels
├── Workflows
│   ├── Active workflows
│   ├── Workflow builder (visual)
│   └── Execution logs
└── Advanced
    ├── API keys
    ├── Webhooks
    └── Integrations
```

---

## 7. API Specifications

### 7.1 API Design Principles

**Tenant-Scoped APIs**:
All endpoints are tenant-aware:
```
POST   /api/v1/tenants/{tenant_id}/subjects
GET    /api/v1/tenants/{tenant_id}/timeline/{subject_id}
POST   /api/v1/tenants/{tenant_id}/events
POST   /api/v1/tenants/{tenant_id}/documents
```

**Tenant Context Resolution**:
```typescript
// Middleware extracts tenant_id from:
// 1. JWT token claims
// 2. Request header: X-Tenant-ID
// 3. Subdomain: acme.timeline.app → tenant_slug = "acme"

app.use(async (req, res, next) => {
  const tenantId =
    req.user?.tenant_id ||           // From JWT
    req.headers['x-tenant-id'] ||    // From header
    await resolveTenantFromSubdomain(req.hostname);

  if (!tenantId) {
    return res.status(400).json({ error: 'Tenant context required' });
  }

  req.tenantId = tenantId;
  await db.raw('SELECT set_tenant_context(?)', [tenantId]);  // Set RLS
  next();
});
```

### 7.2 Authentication Endpoints

#### POST /api/v1/auth/login
```typescript
// Request
{
  email: string;
  password: string;
  tenant_slug?: string;  // Optional, can be inferred from subdomain
}

// Response
{
  success: true,
  data: {
    access_token: string;      // JWT, 15min expiry
    refresh_token: string;     // 7 days
    user: {
      id: string;
      tenant_id: string;
      email: string;
      display_name: string;
      role: string;
      permissions: object;
    },
    tenant: {
      id: string;
      name: string;
      slug: string;
      tier: string;
    }
  }
}
```

### 7.3 Tenant Management (Admin Only)

#### POST /api/v1/tenants (System Admin)
Create new tenant (onboarding)

```typescript
// Request
{
  name: string;
  slug: string;
  industry?: string;
  tier: 'starter' | 'professional' | 'enterprise';
  admin_user: {
    email: string;
    first_name: string;
    last_name: string;
    password: string;
  }
}

// Response
{
  success: true,
  data: {
    tenant: {
      id: string;
      name: string;
      slug: string;
      status: "active"
    },
    admin_user: {
      id: string;
      email: string;
      temporary_password: string;  // If auto-generated
    },
    setup_url: string;  // Link to configuration wizard
  }
}
```

#### GET /api/v1/tenants/{tenant_id}
Get tenant details

#### PATCH /api/v1/tenants/{tenant_id}
Update tenant configuration

### 7.4 Subject Management

#### POST /api/v1/tenants/{tenant_id}/subjects
Create new subject

```typescript
// Request
{
  subject_type: string;      // Must exist in tenant's subject_types
  subject_code?: string;     // Auto-generated if not provided
  display_name: string;
  attributes: object;        // Validated against subject type schema
  tags?: string[];
}

// Response
{
  success: true,
  data: {
    id: string;
    tenant_id: string;
    subject_type: string;
    subject_code: string;    // e.g., "CLIENT-00123"
    display_name: string;
    attributes: object;
    created_at: string;
    _stats: {
      event_count: 0,
      document_count: 0
    }
  }
}
```

#### GET /api/v1/tenants/{tenant_id}/subjects
List subjects with filters

```typescript
// Query Parameters
{
  subject_type?: string;
  search?: string;           // Full-text search
  tags?: string[];
  created_after?: string;    // ISO date
  page?: number;
  limit?: number;            // Max 100
  sort?: string;             // 'created_at:desc', 'display_name:asc'
}

// Response
{
  success: true,
  data: [
    {
      id: string;
      subject_type: string;
      subject_code: string;
      display_name: string;
      attributes: object;
      tags: string[];
      created_at: string;
      _stats: {
        event_count: number;
        document_count: number;
        last_activity: string;
      }
    }
  ],
  meta: {
    pagination: {
      page: 1,
      limit: 50,
      total: 247,
      total_pages: 5
    }
  }
}
```

#### GET /api/v1/tenants/{tenant_id}/subjects/{subject_id}
Get subject with full details

```typescript
// Response
{
  success: true,
  data: {
    id: string;
    subject_type: string;
    subject_code: string;
    display_name: string;
    attributes: object;
    tags: string[];
    created_at: string;
    updated_at: string;

    _stats: {
      event_count: 247,
      document_count: 89,
      first_event_at: "2020-03-15T10:00:00Z",
      last_event_at: "2024-12-13T09:30:00Z",
      timeline_duration: "4 years, 9 months"
    },

    _recent_events: [
      // Last 5 events
    ]
  }
}
```

#### PATCH /api/v1/tenants/{tenant_id}/subjects/{subject_id}
Update subject attributes

```typescript
// Request
{
  display_name?: string;
  attributes?: object;      // Partial update, validated against schema
  tags?: string[];
}
```

### 7.5 Event Management

#### POST /api/v1/tenants/{tenant_id}/events
Create new event (immutable)

```typescript
// Request
{
  subject_id: string;
  event_type: string;        // Must exist in tenant's event_types
  timestamp?: string;        // ISO date, defaults to now
  payload: object;           // Validated against event type schema
  tags?: string[];
  importance?: 'low' | 'normal' | 'high' | 'critical';
  document_ids?: string[];   // Link existing documents
}

// Response
{
  success: true,
  data: {
    id: string;
    tenant_id: string;
    subject_id: string;
    event_type: string;
    timestamp: string;
    recorded_at: string;
    actor_type: "user",
    actor_id: string;
    actor_name: string;
    payload: object;
    hash: string;            // Cryptographic hash
    previous_hash: string;
    sequence_number: number;
    version: number;
    tags: string[];
    created_at: string;

    _workflow_triggered: boolean;  // If any workflows were triggered
  }
}
```

#### GET /api/v1/tenants/{tenant_id}/subjects/{subject_id}/timeline
Get subject's timeline

```typescript
// Query Parameters
{
  from?: string;             // ISO date
  to?: string;
  event_type?: string[];     // Filter by types
  category?: string[];
  importance?: string[];
  tags?: string[];
  milestones_only?: boolean;
  include_documents?: boolean;  // Default: true
  page?: number;
  limit?: number;            // Default: 50
  sort?: 'asc' | 'desc';     // Default: 'desc'
}

// Response
{
  success: true,
  data: {
    subject: {
      id: string;
      subject_code: string;
      display_name: string;
    },
    timeline: [
      {
        id: string;
        event_type: string;
        event_category: string;
        timestamp: string;
        actor_type: string;
        actor_name: string;
        payload: object;
        tags: string[];
        importance: string;
        is_milestone: boolean;
        sequence_number: number;
        documents: [
          {
            id: string;
            filename: string;
            document_category: string;
            file_size: number;
          }
        ]
      }
    ],
    summary: {
      total_events: 247,
      date_range: {
        from: "2020-03-15",
        to: "2024-12-13"
      },
      events_by_type: {
        "PAYMENT_RECEIVED": 89,
        "CLAIM_SUBMITTED": 15,
        // ...
      }
    },
    chain_verified: true  // Cryptographic integrity check
  },
  meta: {
    pagination: {...}
  }
}
```

#### GET /api/v1/tenants/{tenant_id}/events/{event_id}
Get single event

#### POST /api/v1/tenants/{tenant_id}/events/verify-chain
Verify event chain integrity

```typescript
// Request
{
  subject_id: string;
}

// Response
{
  success: true,
  data: {
    chain_valid: boolean,
    total_events: 247,
    first_event_id: string,
    last_event_id: string,
    last_event_hash: string,
    verified_at: string
  }
}
```

### 7.6 Document Management

#### POST /api/v1/tenants/{tenant_id}/documents/upload
Upload document

```typescript
// Request: multipart/form-data
{
  file: File;
  document_category: string;
  subject_ids?: string[];    // Link to subjects
  event_ids?: string[];      // Link to events
  title?: string;
  description?: string;
  metadata?: object;         // Validated against category schema
  document_date?: string;
  expiry_date?: string;
  tags?: string[];
}

// Response
{
  success: true,
  data: {
    id: string;
    filename: string;
    original_filename: string;
    document_category: string;
    file_size: number;
    checksum: string;
    storage_path: string;
    access_url: string;        // Pre-signed URL, 1 hour expiry
    uploaded_at: string;

    _linked_subjects: number;
    _linked_events: number;
  }
}
```

#### GET /api/v1/tenants/{tenant_id}/documents/{document_id}
Get document metadata

#### GET /api/v1/tenants/{tenant_id}/documents/{document_id}/download
Download document (redirects to pre-signed URL)

#### GET /api/v1/tenants/{tenant_id}/subjects/{subject_id}/documents
List documents for subject

### 7.7 Configuration Management

#### GET /api/v1/tenants/{tenant_id}/subject-types
List configured subject types

#### POST /api/v1/tenants/{tenant_id}/subject-types
Create subject type definition

```typescript
// Request
{
  type_name: string;         // Uppercase, e.g., "POLICY"
  display_name: string;
  description?: string;
  schema: object;            // JSON Schema
  icon?: string;
  color?: string;
  has_timeline?: boolean;
  allow_documents?: boolean;
}
```

#### GET /api/v1/tenants/{tenant_id}/event-types
List configured event types

#### POST /api/v1/tenants/{tenant_id}/event-types
Create event type definition

```typescript
// Request
{
  event_type: string;
  display_name: string;
  category?: string;
  payload_schema: object;    // JSON Schema
  is_milestone?: boolean;
  importance?: string;
  triggers_workflow?: string;
}
```

### 7.8 Search API

#### GET /api/v1/tenants/{tenant_id}/search
Global search across subjects, events, documents

```typescript
// Query Parameters
{
  q: string;                 // Search query
  scope?: 'all' | 'subjects' | 'events' | 'documents';
  subject_type?: string[];
  event_type?: string[];
  document_category?: string[];
  from_date?: string;
  to_date?: string;
  limit?: number;
}

// Response
{
  success: true,
  data: {
    subjects: [
      {
        id: string;
        subject_type: string;
        display_name: string;
        highlight: string;     // Matched text with <mark> tags
        score: number;
      }
    ],
    events: [...],
    documents: [...],
    total_results: number
  }
}
```

### 7.9 Analytics & Reporting

#### GET /api/v1/tenants/{tenant_id}/analytics/dashboard
Dashboard statistics

```typescript
// Response
{
  success: true,
  data: {
    subjects: {
      total: 1250,
      by_type: {
        "CLIENT": 850,
        "POLICY": 1200,
        "CLAIM": 95
      },
      new_this_month: 45
    },
    events: {
      total: 125000,
      this_month: 3420,
      by_type: {
        "PAYMENT_RECEIVED": 45000,
        // ...
      }
    },
    documents: {
      total: 8900,
      total_size_gb: 125.4,
      expiring_soon: 12
    },
    activity: {
      recent_events: [...],  // Last 10 events
      active_users: 15
    }
  }
}
```

#### GET /api/v1/tenants/{tenant_id}/analytics/subjects/{subject_id}
Subject analytics

```typescript
// Response
{
  success: true,
  data: {
    timeline_summary: {
      total_events: 247,
      events_by_month: {
        "2024-11": 12,
        "2024-12": 8
      },
      most_common_events: [
        { event_type: "PAYMENT_RECEIVED", count: 89 }
      ]
    },
    activity_heatmap: {
      // Data for visualization
    }
  }
}
```

### 7.10 Webhook Endpoints (Incoming)

#### POST /api/v1/tenants/{tenant_id}/webhooks/{webhook_id}
Receive external webhooks (e.g., payment gateways, insurance platforms)

```typescript
// Validates signature, creates event automatically

// Example: Payment gateway webhook
{
  event_type: "payment.completed",
  data: {
    amount: 5000,
    currency: "USD",
    customer_id: "cust_123",
    transaction_id: "txn_abc"
  },
  signature: "sha256=..."
}

// Timeline auto-creates:
// - Event: PAYMENT_RECEIVED
// - Links to subject via customer_id mapping
// - Triggers workflows if configured
```

---

## 8. Frontend Application

### 8.1 Application Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── App.tsx
│   │   ├── router.tsx
│   │   └── providers.tsx
│   ├── features/
│   │   ├── auth/
│   │   ├── subjects/
│   │   │   ├── SubjectList.tsx
│   │   │   ├── SubjectDetail.tsx
│   │   │   └── SubjectTimeline.tsx
│   │   ├── events/
│   │   │   ├── EventList.tsx
│   │   │   └── CreateEventModal.tsx
│   │   ├── documents/
│   │   │   ├── DocumentUpload.tsx
│   │   │   ├── DocumentViewer.tsx
│   │   │   └── DocumentList.tsx
│   │   ├── configuration/
│   │   │   ├── SubjectTypes.tsx
│   │   │   ├── EventTypes.tsx
│   │   │   └── WorkflowBuilder.tsx
│   │   └── analytics/
│   ├── components/
│   │   ├── Timeline/
│   │   │   ├── TimelineView.tsx
│   │   │   ├── TimelineEvent.tsx
│   │   │   └── TimelineFilters.tsx
│   │   ├── Layout/
│   │   └── Common/
│   ├── hooks/
│   ├── services/
│   │   ├── api.ts
│   │   ├── subjects.ts
│   │   ├── events.ts
│   │   └── documents.ts
│   ├── store/
│   └── types/
```

### 8.2 Key Components

#### Timeline Component (Core Feature)

```typescript
// components/Timeline/TimelineView.tsx
import { Timeline } from 'antd';
import { useTimeline } from '@/hooks/useTimeline';

interface TimelineViewProps {
  tenantId: string;
  subjectId: string;
}

export const TimelineView: React.FC<TimelineViewProps> = ({
  tenantId,
  subjectId
}) => {
  const {
    events,
    isLoading,
    filters,
    setFilters,
    hasMore,
    loadMore,
    chainVerified
  } = useTimeline(tenantId, subjectId);

  if (isLoading && events.length === 0) {
    return <Spin size="large" />;
  }

  return (
    <div className="timeline-container">
      {!chainVerified && (
        <Alert
          type="warning"
          message="Event chain verification failed"
          description="Timeline integrity may be compromised. Contact support."
        />
      )}

      <TimelineFilters
        filters={filters}
        onChange={setFilters}
      />

      <Timeline mode="left">
        {events.map((event) => (
          <TimelineEvent
            key={event.id}
            event={event}
          />
        ))}
      </Timeline>

      {hasMore && (
        <Button onClick={loadMore} loading={isLoading}>
          Load More
        </Button>
      )}
    </div>
  );
};
```

#### Subject Detail Page

```typescript
// features/subjects/SubjectDetail.tsx
export const SubjectDetail: React.FC = () => {
  const { tenant_id, subject_id } = useParams();
  const { subject, isLoading } = useSubject(tenant_id!, subject_id!);

  if (!subject) return <Empty />;

  return (
    <PageContainer>
      <Card
        title={
          <Space>
            <Tag color={getSubjectTypeColor(subject.subject_type)}>
              {subject.subject_type}
            </Tag>
            <Typography.Title level={3}>
              {subject.display_name}
            </Typography.Title>
            <Typography.Text type="secondary">
              {subject.subject_code}
            </Typography.Text>
          </Space>
        }
      >
        <Descriptions column={2}>
          {Object.entries(subject.attributes).map(([key, value]) => (
            <Descriptions.Item key={key} label={key}>
              {String(value)}
            </Descriptions.Item>
          ))}
        </Descriptions>

        <Row gutter={16} style={{ marginTop: 24 }}>
          <Col span={8}>
            <Statistic
              title="Total Events"
              value={subject._stats.event_count}
              prefix={<ClockCircleOutlined />}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="Documents"
              value={subject._stats.document_count}
              prefix={<FileOutlined />}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="Timeline Duration"
              value={subject._stats.timeline_duration}
            />
          </Col>
        </Row>
      </Card>

      <Tabs
        items={[
          {
            key: 'timeline',
            label: 'Timeline',
            children: <TimelineView tenantId={tenant_id!} subjectId={subject_id!} />
          },
          {
            key: 'documents',
            label: 'Documents',
            children: <DocumentList subjectId={subject_id!} />
          },
          {
            key: 'analytics',
            label: 'Analytics',
            children: <SubjectAnalytics subjectId={subject_id!} />
          }
        ]}
      />
    </PageContainer>
  );
};
```

### 8.3 Tenant Branding

**Dynamic branding based on tenant configuration**:

```typescript
// App.tsx - Load tenant branding
const App: React.FC = () => {
  const { tenant } = useTenant();

  useEffect(() => {
    if (tenant?.branding) {
      // Apply custom colors
      document.documentElement.style.setProperty(
        '--primary-color',
        tenant.branding.primary_color || '#1890ff'
      );

      // Update page title
      document.title = tenant.branding.app_name || 'Timeline';

      // Update favicon
      const favicon = document.querySelector("link[rel='icon']");
      if (favicon && tenant.branding.favicon_url) {
        favicon.setAttribute('href', tenant.branding.favicon_url);
      }
    }
  }, [tenant]);

  return <RouterProvider router={router} />;
};
```

**Subdomain-based tenant resolution**:
```
acme-insurance.timeline.app → tenant_slug = "acme-insurance"
hospital-xyz.timeline.app   → tenant_slug = "hospital-xyz"
```

---

## 9. Security & Compliance

### 9.1 Multi-Tenant Security

**Tenant Isolation Layers**:
1. **Database Level**: Row-level security (RLS)
2. **Application Level**: Tenant context middleware
3. **API Level**: Tenant validation in all endpoints
4. **Storage Level**: Tenant-prefixed S3 paths
5. **Cache Level**: Tenant-namespaced Redis keys

**Defense in Depth**:
```typescript
// Even if RLS fails, application layer catches it
async function getSubjects(tenantId: string) {
  // Set RLS context
  await db.raw('SELECT set_tenant_context(?)', [tenantId]);

  // Query (RLS auto-filters)
  const subjects = await db.subjects.findMany();

  // Additional validation (paranoid mode)
  if (subjects.some(s => s.tenant_id !== tenantId)) {
    throw new SecurityError('Tenant isolation breach detected');
  }

  return subjects;
}
```

### 9.2 Event Immutability & Integrity

**Cryptographic Guarantees**:
- SHA-256 hashing of event content
- Blockchain-style chaining
- Optional digital signatures
- Periodic integrity verification

**Compliance Benefits**:
- Non-repudiation (who did what)
- Tamper detection
- Audit trail integrity
- Legal admissibility of records

### 9.3 Data Protection

**Encryption**:
```yaml
at_rest:
  database: PostgreSQL disk encryption (LUKS/AWS RDS encryption)
  documents: S3 server-side encryption (SSE-KMS with tenant-specific keys)
  backups: Encrypted with separate keys

in_transit:
  api: TLS 1.3
  database: SSL/TLS
  storage: HTTPS only

application_layer:
  pii_fields: Encrypted before storage (e.g., SSN, credit cards)
  tenant_keys: Separate encryption keys per tenant
```

**Data Retention**:
```sql
-- Automatic retention enforcement
CREATE TABLE retention_policies (
    tenant_id UUID NOT NULL,
    document_category VARCHAR(100),
    retention_days INTEGER NOT NULL,
    action VARCHAR(50) DEFAULT 'archive'  -- archive, anonymize, delete
);

-- Scheduled job to enforce retention
-- Runs daily, archives/deletes documents past retention period
```

### 9.4 Access Control

**Role-Based Permissions**:
```typescript
const PERMISSIONS = {
  admin: {
    subjects: ['create', 'read', 'update', 'delete'],
    events: ['create', 'read'],  // Cannot update/delete (immutable)
    documents: ['upload', 'read', 'delete'],
    configuration: ['manage'],
    users: ['manage']
  },
  manager: {
    subjects: ['create', 'read', 'update'],
    events: ['create', 'read'],
    documents: ['upload', 'read'],
    configuration: ['read']
  },
  agent: {
    subjects: ['read', 'update'],
    events: ['create', 'read'],
    documents: ['upload', 'read']
  },
  viewer: {
    subjects: ['read'],
    events: ['read'],
    documents: ['read']
  }
};
```

### 9.5 Compliance Features

**GDPR**:
- Right to access: Export subject data
- Right to erasure: Anonymize/delete on request
- Right to portability: JSON/CSV export
- Consent tracking: Via events
- Breach notification: Automated alerts

**SOC 2**:
- Audit logging (all actions logged)
- Access controls (RBAC)
- Encryption (at-rest and in-transit)
- Monitoring and alerting
- Incident response procedures

**HIPAA** (Healthcare):
- PHI encryption
- Access audit trails
- Data retention policies
- BAA agreements
- Minimum necessary access

---

## 10. Infrastructure & Deployment

### 10.1 Production Architecture (AWS Example)

```
┌─────────────────────────────────────────────────────────┐
│                    Route 53 (DNS)                        │
│  *.timeline.app → ALB                                    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│         Application Load Balancer (ALB)                  │
│  - SSL/TLS termination                                   │
│  - Health checks                                         │
│  - Target: ECS Service                                   │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│          ECS Fargate (Auto-scaling)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ API Task │  │ API Task │  │ API Task │              │
│  │(2 vCPU,  │  │(2 vCPU,  │  │(2 vCPU,  │              │
│  │ 4GB RAM) │  │ 4GB RAM) │  │ 4GB RAM) │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
└───────┼────────────┼─────────────┼────────────────────┘
        │            │             │
        └────────────┼─────────────┘
                     │
        ┌────────────▼─────────────┐
        │                           │
┌───────▼─────────┐       ┌────────▼──────────┐
│  RDS PostgreSQL │       │ ElastiCache Redis │
│  (Multi-AZ)     │       │   (Cluster Mode)  │
│  - Primary      │       │   - Sharded       │
│  - Read Replica │       │   - Multi-AZ      │
└─────────────────┘       └───────────────────┘

┌─────────────────────────────────────────────────────────┐
│                  S3 (Document Storage)                    │
│  Buckets:                                                │
│  - timeline-documents-prod/                              │
│    └── tenants/{tenant_id}/documents/                   │
│  - Versioning: Enabled                                   │
│  - Encryption: SSE-KMS                                   │
│  - Lifecycle: Archive to Glacier after 2 years          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              CloudFront CDN (Global)                     │
│  - Edge caching for documents                            │
│  - Custom domain support                                 │
└─────────────────────────────────────────────────────────┘
```

### 10.2 Kubernetes Deployment (Alternative)

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: timeline-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: timeline-api
  template:
    metadata:
      labels:
        app: timeline-api
    spec:
      containers:
      - name: api
        image: timeline/api:latest
        ports:
        - containerPort: 3000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: timeline-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: timeline-secrets
              key: redis-url
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 3000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 3000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: timeline-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: timeline-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### 10.3 Monitoring & Observability

```yaml
monitoring:
  metrics:
    - API response times (p50, p95, p99)
    - Request throughput
    - Error rates by endpoint
    - Database query performance
    - Cache hit rates
    - Event creation rate
    - Document upload volume

  logs:
    - Structured JSON logging
    - Request ID tracing
    - Tenant ID in all logs
    - Error stack traces
    - Audit logs (separate stream)

  alerts:
    - API error rate > 1%
    - Response time p95 > 1s
    - Database CPU > 80%
    - Disk usage > 85%
    - Event chain verification failures
    - Tenant isolation breaches

  tools:
    - Metrics: Prometheus + Grafana / Datadog
    - Logs: ELK Stack / CloudWatch Logs
    - APM: New Relic / Sentry
    - Uptime: Pingdom / UptimeRobot
```

### 10.4 Disaster Recovery

```yaml
backup_strategy:
  database:
    - Automated snapshots every 6 hours
    - Retention: 30 days
    - Point-in-time recovery: 7 days
    - Cross-region replication

  documents:
    - S3 versioning enabled
    - Cross-region replication
    - Glacier archival after 2 years

  recovery_procedures:
    rto: 2 hours   # Recovery Time Objective
    rpo: 30 minutes # Recovery Point Objective

    steps:
      1. Promote read replica to primary
      2. Update DNS to failover region
      3. Restore from latest snapshot
      4. Verify data integrity (event chains)
      5. Resume operations
```

---

## 11. Implementation Roadmap

### 11.1 Phase 1: Core Platform (Months 1-4)

**Month 1: Foundation**
- Project setup and infrastructure
- Database schema implementation
- Multi-tenancy foundation (RLS, tenant context)
- Authentication and basic API structure

**Month 2: Core Entities**
- Subject management (CRUD)
- Event creation and storage
- Cryptographic chaining implementation
- Basic timeline view

**Month 3: Documents & Search**
- Document upload/download
- S3 integration
- Full-text search (PostgreSQL)
- Subject-document-event linking

**Month 4: Polish & Testing**
- Frontend timeline component
- Configuration UI (basic)
- Integration tests
- Security audit
- First tenant onboarding

**Deliverables**:
- ✅ Multi-tenant SaaS platform
- ✅ Subject and event management
- ✅ Immutable event ledger
- ✅ Document storage
- ✅ Timeline visualization
- ✅ 1-3 pilot tenants

### 11.2 Phase 2: Configuration & Automation (Months 5-8)

**Month 5: Configuration Layer**
- Subject type configuration UI
- Event type configuration UI
- Document category management
- Schema validation

**Month 6: Workflows**
- Declarative workflow engine
- Workflow builder UI
- Notification system
- Email integration

**Month 7: Integrations**
- Webhook infrastructure
- External API integrations
- CSV/Excel import
- Data migration tools

**Month 8: Advanced Features**
- Event chain verification API
- Time travel queries
- Bulk operations
- Advanced search

**Deliverables**:
- ✅ Tenant self-service configuration
- ✅ Automated workflows
- ✅ Integration ecosystem
- ✅ 5-10 paying customers

### 11.3 Phase 3: SaaS Features & Scale (Months 9-12)

**Month 9: Billing & Subscriptions**
- Stripe integration
- Tiered pricing (starter, professional, enterprise)
- Usage metering
- Tenant self-service portal

**Month 10: Analytics & Reporting**
- Dashboard analytics
- Custom report builder
- Data export (PDF, Excel, CSV)
- API analytics

**Month 11: Performance & Scale**
- Query optimization
- Caching strategy
- Database partitioning refinement
- Load testing (1000+ concurrent users)

**Month 12: Polish & Launch**
- Mobile responsiveness
- Documentation
- Marketing site
- Public launch

**Deliverables**:
- ✅ Production-ready SaaS product
- ✅ Billing and subscriptions
- ✅ Analytics and reporting
- ✅ 20+ paying customers
- ✅ $10K+ MRR

### 11.4 Post-Launch Roadmap

**Phase 4: Growth Features**
- Mobile apps (iOS, Android)
- Advanced AI features (OCR, auto-categorization)
- Client/provider portals (external access)
- Integration marketplace
- White-label options
- SSO (SAML, OAuth)

---

## 12. Development Guidelines

### 12.1 Code Standards

```typescript
// Tenant context MUST be set for all operations
async function example(tenantId: string, subjectId: string) {
  // Always set tenant context first
  await setTenantContext(tenantId);

  // Then perform operations (RLS auto-enforces)
  const subject = await db.subjects.findUnique({
    where: { id: subjectId }
  });

  // Additional validation (defense in depth)
  if (subject.tenant_id !== tenantId) {
    throw new SecurityError('Tenant mismatch');
  }

  return subject;
}

// Event creation ALWAYS goes through event service
// (to maintain hash chain integrity)
class EventService {
  async createEvent(data: CreateEventDTO): Promise<Event> {
    await setTenantContext(data.tenant_id);

    // Validate event type exists
    const eventType = await this.validateEventType(data.event_type);

    // Validate payload against schema
    await this.validatePayload(data.payload, eventType.payload_schema);

    // Insert (trigger maintains chain)
    const event = await db.events.create({
      data: {
        ...data,
        actor_type: 'user',
        actor_id: getCurrentUser().id,
        actor_name: getCurrentUser().display_name
      }
    });

    // Execute workflows
    await this.executeWorkflows(event);

    return event;
  }
}
```

### 12.2 Testing Strategy

```yaml
unit_tests:
  coverage: 80%+
  focus:
    - Event hash calculation
    - Chain verification
    - Schema validation
    - Tenant isolation logic

integration_tests:
  coverage: 70%+
  focus:
    - API endpoints (all CRUD)
    - Multi-tenant data isolation
    - Event chain integrity
    - Workflow execution

e2e_tests:
  critical_paths:
    - Tenant onboarding
    - Subject creation
    - Event timeline viewing
    - Document upload
    - Configuration management

security_tests:
  - Tenant isolation (attempt cross-tenant access)
  - Event immutability (attempt update/delete)
  - API authentication
  - SQL injection
  - XSS prevention
```

### 12.3 Git Workflow

```yaml
branches:
  main: Production
  develop: Integration
  feature/*: New features
  hotfix/*: Emergency fixes

commit_format: "<type>(<scope>): <subject>"
examples:
  - "feat(events): add cryptographic chaining"
  - "fix(tenancy): resolve RLS policy issue"
  - "docs(api): update event endpoints"

pull_requests:
  required_reviews: 2
  checks:
    - All tests pass
    - Coverage > 80%
    - No security vulnerabilities
    - Documentation updated
```

---

## Appendices

### Appendix A: Glossary

**Tenant**: An organization using Timeline (multi-tenant SaaS model)

**Subject**: Anything that can have a history (client, policy, employee, etc.)

**Event**: Immutable fact about what happened, when, and to whom

**Event Chain**: Cryptographically linked sequence of events (blockchain-style)

**Document**: Versioned artifact providing evidence (files, PDFs, images)

**Event Sourcing**: Architectural pattern where state changes are stored as events

**Row-Level Security (RLS)**: Database-level access control filtering rows by tenant

**Immutability**: Events cannot be modified or deleted after creation

**Cryptographic Chaining**: Each event contains hash of previous event

**Multi-Tenancy**: Single application instance serving multiple organizations

### Appendix B: Performance Benchmarks

**Target Metrics**:
- API response time (p95): < 500ms
- Timeline load (1000 events): < 2s
- Document upload (10MB): < 10s
- Full-text search: < 300ms
- Event creation: < 200ms
- Concurrent tenants: 1000+
- Events per second: 1000+

### Appendix C: Cost Estimation

**Infrastructure Costs (AWS, 100 tenants)**:
```yaml
compute:
  ecs_fargate: $300/month (3 tasks × $100)
database:
  rds_postgresql: $400/month (db.r5.large, Multi-AZ)
cache:
  elasticache_redis: $150/month (cache.r5.large)
storage:
  s3_documents: $50-$500/month (depending on volume)
  rds_storage: $100/month (1TB)
networking:
  data_transfer: $100/month
  cloudfront: $50/month
monitoring:
  cloudwatch: $50/month
total: ~$1,200-$1,650/month

per_tenant_marginal_cost: ~$5-10/month
target_price_per_tenant: $99-$499/month (depending on tier)
gross_margin: 80-90%
```

### Appendix D: Migration Checklist

**Onboarding New Tenant**:
- [ ] Create tenant record
- [ ] Initialize default configurations (subject types, event types)
- [ ] Create admin user
- [ ] Send welcome email with setup guide
- [ ] Import historical data (if applicable)
- [ ] Configure integrations
- [ ] Train users
- [ ] Go live

---

**END OF TECHNICAL SPECIFICATION**

**Next Steps**:
1. Review and approve specification
2. Set up development environment
3. Begin Phase 1 implementation
4. Recruit development team (if needed)
5. Establish project management process

For questions or clarifications, contact the project team.
