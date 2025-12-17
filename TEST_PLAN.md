# Timeline System - Test Plan

## MVP Readiness Assessment

### ✅ Implemented Features
- Multi-tenancy with data isolation
- User authentication (JWT + bcrypt)
- Event sourcing with cryptographic chaining
- Chain verification (tamper detection)
- Schema registry (JSON Schema validation)
- RBAC system (roles, permissions, user roles)
- Document storage (local filesystem)
- Workflow automation (event-driven)
- Logging infrastructure

### ⚠️ Not Yet Tested
- Integration tests
- End-to-end tests
- Load/performance testing
- Real-world data validation
- Error handling edge cases
- Security audit
- Backup/recovery procedures

---

## Phase 1: Core Functionality Testing (2-3 days)

### 1.1 Authentication & Authorization Tests

**Create test file**: `tests/integration/test_auth_flow.py`

```python
async def test_user_registration_and_login():
    """Test complete auth flow"""
    # 1. Create tenant
    # 2. Register user
    # 3. Login and get JWT
    # 4. Access protected endpoint
    # 5. Verify JWT expiration
    pass

async def test_rbac_permissions():
    """Test RBAC enforcement"""
    # 1. Create user with viewer role
    # 2. Attempt to create event (should fail)
    # 3. Grant create permission
    # 4. Create event (should succeed)
    pass

async def test_tenant_isolation():
    """Ensure tenants can't access each other's data"""
    # 1. Create two tenants with users
    # 2. User A creates event
    # 3. User B tries to access it (should fail)
    pass
```

### 1.2 Event Sourcing Tests

**Create test file**: `tests/integration/test_event_sourcing.py`

```python
async def test_event_chain_integrity():
    """Test cryptographic chain"""
    # 1. Create subject
    # 2. Create 10 events
    # 3. Verify chain links
    # 4. Tamper with event 5
    # 5. Verification should detect tampering
    pass

async def test_schema_validation():
    """Test schema enforcement"""
    # 1. Create schema for payment_received
    # 2. Create valid event (should succeed)
    # 3. Create invalid event (should fail)
    # 4. Update schema version
    # 5. Test backward compatibility
    pass

async def test_concurrent_event_creation():
    """Test race conditions"""
    # 1. Create subject
    # 2. Create 100 events concurrently
    # 3. Verify no chain breaks
    # 4. Verify all events stored
    pass
```

### 1.3 Workflow Automation Tests

**Create test file**: `tests/integration/test_workflows.py`

```python
async def test_workflow_triggering():
    """Test workflow execution"""
    # 1. Create workflow for urgent issues
    # 2. Create matching event
    # 3. Verify workflow executed
    # 4. Check execution log
    pass

async def test_workflow_conditions():
    """Test conditional triggering"""
    # 1. Create workflow with conditions
    # 2. Create non-matching event (no trigger)
    # 3. Create matching event (should trigger)
    pass

async def test_infinite_loop_prevention():
    """Test workflow safety"""
    # 1. Create workflow that creates events
    # 2. Trigger it
    # 3. Verify it doesn't loop infinitely
    pass
```

### 1.4 Document Storage Tests

**Create test file**: `tests/integration/test_documents.py`

```python
async def test_document_upload_and_retrieval():
    """Test file operations"""
    # 1. Upload PDF document
    # 2. Verify checksum
    # 3. Download document
    # 4. Compare checksums
    pass

async def test_document_versioning():
    """Test version management"""
    # 1. Upload document v1
    # 2. Upload document v2
    # 3. Retrieve both versions
    # 4. Soft delete v1
    pass
```

---

## Phase 2: Real-World Scenario Testing (1-2 days)

### 2.1 Email Activity Test Case

**Scenario**: Single user email account monitoring

**Setup**:
1. Create tenant: "personal_email"
2. Create subject: "user@example.com"
3. Define schemas:
   - email_received
   - email_sent
   - email_read
   - email_archived

**Test Data** (use sample data, not real emails):
```json
[
  {
    "event_type": "email_received",
    "subject_id": "user@example.com",
    "payload": {
      "from": "friend@example.com",
      "subject": "Lunch tomorrow?",
      "timestamp": "2025-12-17T10:00:00Z",
      "message_id": "msg_001",
      "labels": ["inbox"]
    }
  },
  {
    "event_type": "email_read",
    "subject_id": "user@example.com",
    "payload": {
      "message_id": "msg_001",
      "read_at": "2025-12-17T10:05:00Z"
    }
  }
]
```

**Test Workflow**:
```json
{
  "name": "Auto-archive old emails",
  "trigger_event_type": "email_received",
  "trigger_conditions": {
    "payload.labels": "inbox"
  },
  "actions": [{
    "type": "create_event",
    "params": {
      "event_type": "email_archived",
      "payload": {
        "message_id": "{{ payload.message_id }}",
        "archived_at": "{{ now() }}"
      }
    }
  }]
}
```

**Test Script**: `tests/scenarios/test_email_tracking.py`

```python
async def test_email_lifecycle():
    """Test complete email activity tracking"""
    # 1. Create 100 sample emails
    # 2. Track read status
    # 3. Verify chain integrity
    # 4. Query timeline
    # 5. Verify workflow execution
    pass
```

### 2.2 Performance Testing

**Load Test Script**: `tests/performance/test_load.py`

```python
async def test_concurrent_users():
    """Test system under load"""
    # 1. Simulate 10 concurrent users
    # 2. Each creates 100 events
    # 3. Measure response times
    # 4. Verify data integrity
    # Target: <200ms per event creation
    pass

async def test_large_timeline_query():
    """Test query performance"""
    # 1. Create subject with 10,000 events
    # 2. Query timeline with pagination
    # 3. Measure response times
    # Target: <500ms for 100 events
    pass
```

---

## Phase 3: Security & Reliability (1-2 days)

### 3.1 Security Testing

**Test file**: `tests/security/test_security.py`

```python
async def test_sql_injection_prevention():
    """Test SQL injection protection"""
    # 1. Attempt SQL injection in event payload
    # 2. Attempt injection in subject_id
    # 3. Verify system sanitizes input
    pass

async def test_jwt_security():
    """Test JWT vulnerabilities"""
    # 1. Attempt token tampering
    # 2. Test expired tokens
    # 3. Test invalid signatures
    # 4. Test token reuse after logout
    pass

async def test_tenant_data_leakage():
    """Test tenant isolation"""
    # 1. Create events in tenant A
    # 2. User from tenant B attempts access
    # 3. Verify complete isolation
    pass
```

### 3.2 Data Integrity Testing

**Test file**: `tests/integration/test_data_integrity.py`

```python
async def test_chain_verification_comprehensive():
    """Test tamper detection"""
    # 1. Create 1000-event chain
    # 2. Modify event #500 directly in DB
    # 3. Run verification
    # 4. Verify detection and reporting
    pass

async def test_schema_migration():
    """Test schema evolution"""
    # 1. Create schema v1
    # 2. Create events with v1
    # 3. Create schema v2 (backward compatible)
    # 4. Verify old events still valid
    pass
```

---

## Phase 4: Production Readiness (1 day)

### 4.1 Missing Features for Production

**High Priority**:
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Rate limiting (prevent abuse)
- [ ] Request validation middleware
- [ ] Database connection pooling optimization
- [ ] Comprehensive error messages
- [ ] Health check endpoints
- [ ] Metrics endpoint (Prometheus format)

**Medium Priority**:
- [ ] Database backup strategy
- [ ] Log aggregation (e.g., ELK stack)
- [ ] Monitoring/alerting (e.g., Grafana)
- [ ] API versioning strategy
- [ ] Pagination cursor support

**Create**: `production_checklist.md`

### 4.2 Deployment Testing

**Test on staging environment**:
```bash
# 1. Deploy to staging
docker-compose up -d

# 2. Run migration
alembic upgrade head

# 3. Seed RBAC
python -m scripts.seed_rbac

# 4. Create test tenant
curl -X POST http://localhost:8000/tenants/

# 5. Run integration tests
pytest tests/integration/ -v

# 6. Check logs
docker logs timeline-api

# 7. Verify database integrity
psql -h localhost -U timeline -c "SELECT COUNT(*) FROM event;"
```

---

## Phase 5: Email Integration Pilot (2-3 days)

### 5.1 Gmail API Integration

**Create**: `integrations/gmail_sync.py`

```python
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class GmailEventSync:
    """Sync Gmail activity to Timeline"""

    async def sync_mailbox(self, user_email: str, tenant_id: str):
        """Sync emails to events"""
        # 1. Authenticate with Gmail API
        # 2. Fetch emails from last sync
        # 3. Transform to Timeline events
        # 4. Create events via API
        # 5. Update last_sync_timestamp
        pass

    async def setup_webhook(self, user_email: str):
        """Setup Gmail push notifications"""
        # 1. Register webhook endpoint
        # 2. Subscribe to mailbox changes
        # 3. Handle incoming notifications
        pass
```

**Test Script**: `tests/integration/test_gmail_integration.py`

```python
async def test_gmail_event_transformation():
    """Test email → event conversion"""
    # Use mock Gmail API responses
    pass

async def test_incremental_sync():
    """Test sync only new emails"""
    # 1. Initial sync (100 emails)
    # 2. Wait for new email
    # 3. Incremental sync (1 email)
    pass
```

### 5.2 Pilot Deployment Plan

**Week 1: Single User (You)**
- Day 1-2: Setup Gmail API access
- Day 3-4: Initial mailbox sync (historical data)
- Day 5-7: Monitor real-time sync, verify accuracy

**Success Criteria**:
- ✅ All emails synced correctly
- ✅ No duplicate events
- ✅ Chain integrity maintained
- ✅ Workflows execute as expected
- ✅ No performance issues (<200ms per event)

**Monitoring**:
```bash
# Check event count
curl http://localhost:8000/events/ | jq '.[] | .event_type' | sort | uniq -c

# Verify chain integrity
curl http://localhost:8000/events/verify/tenant/all

# Check workflow executions
curl http://localhost:8000/workflows/{workflow_id}/executions
```

---

## Testing Tools & Setup

### Required Tools
```bash
# Testing
pip install pytest pytest-asyncio pytest-cov httpx faker

# Load testing
pip install locust

# Security testing
pip install safety bandit

# API documentation
pip install fastapi[all]  # Includes Swagger UI
```

### Test Database Setup
```bash
# Create test database
createdb timeline_test

# Set test environment
export DATABASE_URL="postgresql://user:pass@localhost/timeline_test"
export SECRET_KEY="test_secret_key_change_in_production"
```

### Running Tests
```bash
# Unit tests
pytest tests/services/ -v

# Integration tests
pytest tests/integration/ -v --cov=.

# Load tests
locust -f tests/performance/locustfile.py

# Security scan
bandit -r . -ll
safety check
```

---

## Risk Assessment

### High Risk (Must Fix Before Production)
1. **No integration tests** → Write comprehensive tests (Phase 1)
2. **No rate limiting** → Add middleware
3. **No backup strategy** → Implement automated backups
4. **No monitoring** → Setup logging + metrics

### Medium Risk (Can Launch With)
1. **Performance not tested** → Monitor in production
2. **Limited error handling** → Improve iteratively
3. **No API versioning** → Add when needed

### Low Risk (Future Enhancement)
1. **Only local storage** → S3 migration later
2. **Basic workflow actions** → Add more types later
3. **No GraphQL** → REST API sufficient for MVP

---

## Go/No-Go Decision Criteria

### ✅ Ready for Pilot (Email Test)
- [ ] Integration tests pass (>80% coverage)
- [ ] RBAC working correctly
- [ ] Chain verification working
- [ ] API documentation complete
- [ ] Basic monitoring in place
- [ ] Backup strategy defined

### ✅ Ready for Production (Multi-User)
- [ ] All pilot tests successful
- [ ] Performance tests pass (<200ms)
- [ ] Security audit complete
- [ ] 99.9% uptime for 1 week
- [ ] User feedback incorporated
- [ ] Rollback plan tested

---

## Timeline Estimate

| Phase | Duration | Parallel Work Possible |
|-------|----------|----------------------|
| Phase 1: Core Testing | 2-3 days | Yes (unit + integration) |
| Phase 2: Scenarios | 1-2 days | No |
| Phase 3: Security | 1-2 days | Yes (with Phase 2) |
| Phase 4: Production Prep | 1 day | No |
| Phase 5: Email Pilot | 2-3 days | No |
| **Total** | **7-11 days** | Can compress to 5-7 days with parallel work |

**Recommendation**: Spend 3-5 days on testing before email pilot to avoid discovering issues with real data.
