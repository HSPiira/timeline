# Timeline System Architecture

## Dependency Inversion Principle (DIP) Implementation

This document describes how the Timeline system follows the Dependency Inversion Principle through protocol-based abstractions.

### Core Principle

> High-level modules should not depend on low-level modules. Both should depend on abstractions.

### Protocol Definitions

All repository and service interfaces are defined as Protocol types in [`core/protocols.py`](core/protocols.py):

#### IHashService
```python
class IHashService(Protocol):
    """Protocol for hash computation services"""
    def compute_hash(
        self,
        tenant_id: str,
        subject_id: str,
        event_type: str,
        event_time: datetime,
        payload: dict,
        previous_hash: Optional[str]
    ) -> str:
        """Compute cryptographic hash for event data"""
```

#### IEventRepository
```python
class IEventRepository(Protocol):
    """Protocol for event repository"""
    async def get_last_event(
        self, subject_id: str, tenant_id: str
    ) -> Optional[Event]:
        """Get the most recent event for a subject"""

    async def create_event(
        self,
        tenant_id: str,
        data: EventCreate,
        event_hash: str,
        previous_hash: Optional[str]
    ) -> Event:
        """Create a new event with computed hash"""
```

#### ISubjectRepository
```python
class ISubjectRepository(Protocol):
    """Protocol for subject repository"""
    async def get_by_id_and_tenant(
        self, subject_id: str, tenant_id: str
    ) -> Optional[Subject]:
        """Get subject by ID and verify tenant ownership"""
```

#### IEventSchemaRepository
```python
class IEventSchemaRepository(Protocol):
    """Protocol for event schema repository"""
    async def get_by_version(
        self, tenant_id: str, event_type: str, version: int
    ) -> Optional[EventSchema]:
        """Get specific schema version"""
```

### Service Layer

The `EventService` depends only on abstractions (protocols), not concrete implementations:

```python
class EventService:
    """Event service following DIP - depends on abstractions, not concretions"""

    def __init__(
        self,
        event_repo: IEventRepository,           # ✅ Protocol
        hash_service: IHashService,             # ✅ Protocol
        subject_repo: ISubjectRepository,       # ✅ Protocol
        schema_repo: Optional[IEventSchemaRepository] = None,  # ✅ Protocol
        workflow_engine: Optional["WorkflowEngine"] = None
    ) -> None:
        self.event_repo = event_repo
        self.hash_service = hash_service
        self.subject_repo = subject_repo
        self.schema_repo = schema_repo
        self.workflow_engine = workflow_engine
```

### Benefits of This Architecture

1. **No Direct Database Access**
   - Before: `await self.event_repo.db.execute(select(Subject)...)`
   - After: `await self.subject_repo.get_by_id_and_tenant(subject_id, tenant_id)`

2. **Easy Testing**
   - Mock protocols instead of concrete repositories
   - No need for database fixtures in unit tests

3. **Loose Coupling**
   - Service layer doesn't know about SQLAlchemy
   - Can swap implementations without changing service code

4. **Clear Contracts**
   - Protocol defines exactly what the service needs
   - Repository can have additional methods not used by service

### Dependency Injection

Dependencies are injected via FastAPI's dependency injection system in [`api/deps.py`](api/deps.py):

```python
async def get_event_service(
    db: AsyncSession = Depends(get_db)
) -> EventService:
    """Event service dependency"""
    event_repo = EventRepository(db)
    subject_repo = SubjectRepository(db)
    schema_repo = EventSchemaRepository(db)

    return EventService(
        event_repo=event_repo,
        hash_service=HashService(),
        subject_repo=subject_repo,
        schema_repo=schema_repo
    )
```

### Repository Implementation

Repositories implement the protocols but can have additional methods:

```python
class SubjectRepository(BaseRepository[Subject]):
    """Repository for Subject entity following LSP"""

    async def get_by_id_and_tenant(
        self, subject_id: str, tenant_id: str
    ) -> Optional[Subject]:
        """Implements ISubjectRepository protocol"""
        result = await self.db.execute(
            select(Subject).where(
                Subject.id == subject_id,
                Subject.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    # Additional methods not in protocol
    async def get_by_external_ref(
        self, tenant_id: str, external_ref: str
    ) -> Optional[Subject]:
        """Repository-specific method"""
        ...
```

### Event Immutability and Security

Events are immutable at multiple layers:

1. **Database Level**
   ```python
   CheckConstraint('created_at IS NOT NULL', name='ck_event_created_at_immutable')
   ```

2. **ORM Level**
   ```python
   @event.listens_for(Event, 'before_update')
   def prevent_event_updates(mapper, connection, target):
       raise ValueError("Events are immutable and cannot be updated.")
   ```

3. **Service Level**
   - Temporal ordering validation
   - Hash chain integrity verification
   - Previous event existence validation

### Testing Strategy

Unit tests can mock protocols:

```python
class MockSubjectRepo:
    async def get_by_id_and_tenant(self, subject_id: str, tenant_id: str):
        return Subject(id=subject_id, tenant_id=tenant_id)

# Test service without database
service = EventService(
    event_repo=MockEventRepo(),
    hash_service=MockHashService(),
    subject_repo=MockSubjectRepo(),
    schema_repo=None
)
```

### Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│              API Layer (FastAPI)                │
│  - Events API                                   │
│  - Subjects API                                 │
│  - Schemas API                                  │
└─────────────────┬───────────────────────────────┘
                  │ Depends on
                  ▼
┌─────────────────────────────────────────────────┐
│           Service Layer (Business Logic)        │
│  - EventService (depends on protocols)          │
│  - WorkflowEngine                               │
│  - AuthorizationService                         │
└─────────────────┬───────────────────────────────┘
                  │ Uses
                  ▼
┌─────────────────────────────────────────────────┐
│         Protocol Layer (Abstractions)           │
│  - IEventRepository                             │
│  - ISubjectRepository                           │
│  - IEventSchemaRepository                       │
│  - IHashService                                 │
└─────────────────┬───────────────────────────────┘
                  │ Implemented by
                  ▼
┌─────────────────────────────────────────────────┐
│    Repository Layer (Data Access)               │
│  - EventRepository                              │
│  - SubjectRepository                            │
│  - EventSchemaRepository                        │
│  - HashService                                  │
└─────────────────┬───────────────────────────────┘
                  │ Uses
                  ▼
┌─────────────────────────────────────────────────┐
│         Database Layer (SQLAlchemy)             │
│  - Event Model                                  │
│  - Subject Model                                │
│  - EventSchema Model                            │
└─────────────────────────────────────────────────┘
```

### Key Files

- [`core/protocols.py`](core/protocols.py) - Protocol definitions
- [`services/event_service.py`](services/event_service.py) - Service implementation
- [`repositories/event_repo.py`](repositories/event_repo.py) - Repository implementation
- [`repositories/subject_repo.py`](repositories/subject_repo.py) - Subject repository
- [`repositories/event_schema_repo.py`](repositories/event_schema_repo.py) - Schema repository
- [`api/deps.py`](api/deps.py) - Dependency injection setup
- [`models/event.py`](models/event.py) - Event model with immutability enforcement

### Security Features

1. **Prevention First**
   - Validates chain integrity at insert time (O(1))
   - Enforces temporal ordering
   - Prevents tampering at database level

2. **Immutability Enforcement**
   - Database constraints
   - ORM-level listeners
   - Service-level validation

3. **Defense in Depth**
   ```
   User Input → API Validation → Service Validation → ORM Protection → DB Constraints
   ```

### Migration Notes

When adding new repository methods:

1. Add method signature to protocol in `core/protocols.py`
2. Implement method in concrete repository
3. Use protocol type in service constructor
4. Update dependency injection in `api/deps.py`

This ensures all layers remain loosely coupled and testable.

Email Categorization with Workflows
Workflows trigger on email_received events and can filter by labels using trigger_conditions. Here are practical examples:
1. Personal Email Handler

POST /api/workflows
Content-Type: application/json
X-Tenant-ID: <your-tenant-id>
Authorization: Bearer <your-token>

{
  "name": "Process Personal Emails",
  "description": "Auto-tag and create follow-up event for personal emails",
  "trigger_event_type": "email_received",
  "trigger_conditions": {
    "payload.labels": {
      "$contains": "CATEGORY_PERSONAL"
    }
  },
  "actions": [
    {
      "type": "create_event",
      "params": {
        "event_type": "email_categorized",
        "payload": {
          "category": "personal",
          "priority": "normal",
          "auto_tagged": true
        }
      }
    }
  ],
  "is_active": true,
  "execution_order": 10
}
2. Important/Urgent Email Escalation

{
  "name": "Escalate Important Emails",
  "description": "Auto-escalate emails marked as important",
  "trigger_event_type": "email_received",
  "trigger_conditions": {
    "$and": [
      {
        "payload.labels": {
          "$contains": "IMPORTANT"
        }
      },
      {
        "payload.is_read": false
      }
    ]
  },
  "actions": [
    {
      "type": "create_event",
      "params": {
        "event_type": "email_escalated",
        "payload": {
          "reason": "marked_important",
          "escalated_at": "{{event_time}}",
          "requires_action": true
        }
      }
    },
    {
      "type": "notify",
      "params": {
        "channel": "email",
        "message": "Important unread email from {{payload.from}}"
      }
    }
  ],
  "is_active": true,
  "execution_order": 5
}
3. Promotional Email Auto-Archive

{
  "name": "Auto-Archive Promotions",
  "description": "Automatically archive promotional emails after 7 days",
  "trigger_event_type": "email_received",
  "trigger_conditions": {
    "$or": [
      {
        "payload.labels": {
          "$contains": "CATEGORY_PROMOTIONS"
        }
      },
      {
        "payload.labels": {
          "$contains": "CATEGORY_UPDATES"
        }
      }
    ]
  },
  "actions": [
    {
      "type": "create_event",
      "params": {
        "event_type": "email_auto_archived",
        "payload": {
          "archived_reason": "promotional_content",
          "retention_days": 7
        }
      }
    }
  ],
  "is_active": true,
  "execution_order": 100,
  "max_executions_per_day": 1000
}
4. Social Media Notification Aggregator

{
  "name": "Aggregate Social Notifications",
  "description": "Group social media emails for daily digest",
  "trigger_event_type": "email_received",
  "trigger_conditions": {
    "payload.labels": {
      "$contains": "CATEGORY_SOCIAL"
    }
  },
  "actions": [
    {
      "type": "create_event",
      "params": {
        "event_type": "social_notification_received",
        "payload": {
          "platform": "{{payload.provider_metadata.platform}}",
          "digest_eligible": true,
          "notification_type": "social"
        }
      }
    }
  ],
  "is_active": true,
  "execution_order": 50
}
5. Unread Email Reminder

{
  "name": "Remind Unread Emails After 24h",
  "description": "Create reminder event for unread important emails",
  "trigger_event_type": "email_received",
  "trigger_conditions": {
    "$and": [
      {
        "payload.is_read": false
      },
      {
        "$or": [
          {
            "payload.labels": {
              "$contains": "IMPORTANT"
            }
          },
          {
            "payload.labels": {
              "$contains": "CATEGORY_PERSONAL"
            }
          }
        ]
      }
    ]
  },
  "actions": [
    {
      "type": "schedule_event",
      "params": {
        "delay_hours": 24,
        "event_type": "email_reminder",
        "payload": {
          "message_id": "{{payload.message_id}}",
          "reminder_reason": "unread_24h"
        }
      }
    }
  ],
  "is_active": true,
  "execution_order": 20
}
Condition Operators
Timeline workflows support these JSONPath operators:
Operator	Description	Example
$contains	Array contains value	{"labels": {"$contains": "INBOX"}}
$eq	Equals	{"is_read": {"$eq": true}}
$ne	Not equals	{"is_starred": {"$ne": false}}
$gt	Greater than	{"attachment_count": {"$gt": 0}}
$lt	Less than	{"size_kb": {"$lt": 100}}
$and	Logical AND	{"$and": [{...}, {...}]}
$or	Logical OR	{"$or": [{...}, {...}]}
Action Types
Available workflow actions:
create_event - Create a new event
notify - Send notification (email, webhook, etc.)
schedule_event - Create delayed/scheduled event
update_subject - Modify subject metadata
trigger_workflow - Chain to another workflow
Best Practices
Use Execution Order - Lower numbers run first (5, 10, 20, ...)
Rate Limiting - Set max_executions_per_day for high-volume workflows
Specific Conditions - Be precise to avoid unwanted triggers
Chain Workflows - Keep individual workflows focused, chain for complex logic
Monitor Executions - Check WorkflowExecution table for debugging