# Email Activity Tracking - Integration Design

## Philosophy: Configuration Over Code

Timeline doesn't need email-specific models. Instead, we **configure** the generic Subject/Event system for email use cases.

---

## Core Models (Already Exist)

### 1. Subject = Email Account
```python
Subject(
    id="cuid_xyz",
    tenant_id="personal",
    subject_type="email_account",  # Configuration, not new model
    external_ref="user@gmail.com"   # Optional: link to email provider
)
```

### 2. Event = Email Activity
```python
Event(
    subject_id="cuid_xyz",  # The email account
    event_type="email_received",
    payload={
        "message_id": "msg_abc123",
        "from": "friend@example.com",
        "to": ["user@gmail.com"],
        "subject": "Lunch tomorrow?",
        "timestamp": "2025-12-17T10:00:00Z",
        "labels": ["inbox", "important"],
        "thread_id": "thread_789",
        "has_attachments": true,
        "size_bytes": 4523
    }
)
```

### 3. EventSchema = Email Event Validation
```json
{
  "event_type": "email_received",
  "version": 1,
  "schema_definition": {
    "type": "object",
    "properties": {
      "message_id": {"type": "string"},
      "from": {"type": "string", "format": "email"},
      "to": {"type": "array", "items": {"type": "string"}},
      "subject": {"type": "string"},
      "timestamp": {"type": "string", "format": "date-time"},
      "labels": {"type": "array", "items": {"type": "string"}},
      "thread_id": {"type": "string"},
      "has_attachments": {"type": "boolean"},
      "size_bytes": {"type": "integer"}
    },
    "required": ["message_id", "from", "to", "timestamp"]
  }
}
```

---

## Optional: Query Optimization Models (Projections)

These are **derived models** (projections/views) for performance, NOT core domain models.

### Option 1: Materialized View (Database Level)

**Purpose**: Fast queries without scanning all events

```sql
CREATE MATERIALIZED VIEW email_summary AS
SELECT
    subject_id,
    COUNT(*) FILTER (WHERE event_type = 'email_received') as received_count,
    COUNT(*) FILTER (WHERE event_type = 'email_sent') as sent_count,
    COUNT(*) FILTER (WHERE event_type = 'email_read'
                      AND payload->>'message_id' IN (
                        SELECT payload->>'message_id'
                        FROM event
                        WHERE event_type = 'email_received'
                      )) as read_count,
    MAX(event_time) as last_activity,
    json_agg(DISTINCT payload->>'labels') as all_labels
FROM event
WHERE subject_id IN (SELECT id FROM subject WHERE subject_type = 'email_account')
GROUP BY subject_id;

-- Refresh periodically
REFRESH MATERIALIZED VIEW email_summary;
```

### Option 2: Python Projection Model (Application Level)

**Purpose**: Type-safe queries, caching

```python
# models/projections/email_projection.py
from sqlalchemy import Column, String, Integer, DateTime, ARRAY
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class EmailAccountProjection(Base):
    """
    Read-only projection of email account state.
    Rebuilt from events periodically.
    """
    __tablename__ = "email_account_projection"

    subject_id = Column(String, primary_key=True)
    email_address = Column(String, nullable=False)

    # Counts
    total_received = Column(Integer, default=0)
    total_sent = Column(Integer, default=0)
    total_read = Column(Integer, default=0)
    total_archived = Column(Integer, default=0)
    unread_count = Column(Integer, default=0)

    # Metadata
    last_received_at = Column(DateTime)
    last_sent_at = Column(DateTime)
    active_labels = Column(ARRAY(String))

    # Stats
    avg_response_time_minutes = Column(Integer)
    most_frequent_sender = Column(String)

    # Rebuild timestamp
    projected_at = Column(DateTime, nullable=False)
```

**Rebuild Service**:
```python
# services/email_projection_service.py
from sqlalchemy import select
from models.event import Event
from models.projections.email_projection import EmailAccountProjection

class EmailProjectionService:
    """Rebuild email projections from events"""

    async def rebuild_projection(self, subject_id: str):
        """Rebuild projection for email account"""
        # 1. Get all events for subject
        events = await self.event_repo.get_by_subject(subject_id)

        # 2. Compute aggregates
        received = [e for e in events if e.event_type == 'email_received']
        sent = [e for e in events if e.event_type == 'email_sent']
        read_ids = {e.payload['message_id'] for e in events if e.event_type == 'email_read'}

        received_ids = {e.payload['message_id'] for e in received}
        unread = received_ids - read_ids

        # 3. Update or create projection
        projection = EmailAccountProjection(
            subject_id=subject_id,
            total_received=len(received),
            total_sent=len(sent),
            total_read=len(read_ids),
            unread_count=len(unread),
            last_received_at=max((e.event_time for e in received), default=None),
            last_sent_at=max((e.event_time for e in sent), default=None),
            projected_at=datetime.now(UTC)
        )

        await self.db.merge(projection)
        await self.db.commit()
```

---

## Integration Layer

### Gmail API Sync Service

```python
# integrations/gmail/gmail_sync.py
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, UTC
from typing import List
import asyncio

class GmailSyncService:
    """Sync Gmail activity to Timeline events"""

    def __init__(
        self,
        timeline_api_client,  # HTTPx client to Timeline API
        credentials: Credentials
    ):
        self.timeline_client = timeline_api_client
        self.gmail = build('gmail', 'v1', credentials=credentials)

    async def sync_mailbox(
        self,
        user_email: str,
        subject_id: str,
        since: datetime = None
    ) -> dict:
        """
        Sync Gmail mailbox to Timeline events.

        Args:
            user_email: Gmail address
            subject_id: Timeline subject ID for this email account
            since: Only sync emails after this timestamp

        Returns:
            Sync summary statistics
        """
        stats = {
            'emails_synced': 0,
            'events_created': 0,
            'errors': []
        }

        # 1. Fetch messages from Gmail
        query = self._build_query(since)
        messages = self._fetch_messages(user_email, query)

        # 2. Transform each message to Timeline events
        for msg_id in messages:
            try:
                events = await self._transform_message_to_events(
                    user_email, msg_id, subject_id
                )

                # 3. Create events via Timeline API
                for event in events:
                    await self.timeline_client.post('/events/', json=event)
                    stats['events_created'] += 1

                stats['emails_synced'] += 1

            except Exception as e:
                stats['errors'].append({
                    'message_id': msg_id,
                    'error': str(e)
                })

        return stats

    async def _transform_message_to_events(
        self,
        user_email: str,
        message_id: str,
        subject_id: str
    ) -> List[dict]:
        """Transform Gmail message to Timeline events"""
        # Fetch full message
        message = self.gmail.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in message['payload']['headers']}

        events = []

        # Event 1: email_received or email_sent
        if 'SENT' in message['labelIds']:
            events.append({
                'subject_id': subject_id,
                'event_type': 'email_sent',
                'event_time': self._parse_date(headers.get('Date')).isoformat(),
                'payload': {
                    'message_id': message_id,
                    'thread_id': message.get('threadId'),
                    'to': headers.get('To', '').split(','),
                    'cc': headers.get('Cc', '').split(',') if headers.get('Cc') else [],
                    'subject': headers.get('Subject', ''),
                    'timestamp': headers.get('Date'),
                    'labels': message.get('labelIds', []),
                    'has_attachments': self._has_attachments(message),
                    'size_bytes': message.get('sizeEstimate', 0)
                }
            })
        else:
            events.append({
                'subject_id': subject_id,
                'event_type': 'email_received',
                'event_time': self._parse_date(headers.get('Date')).isoformat(),
                'payload': {
                    'message_id': message_id,
                    'thread_id': message.get('threadId'),
                    'from': headers.get('From', ''),
                    'to': [user_email],
                    'subject': headers.get('Subject', ''),
                    'timestamp': headers.get('Date'),
                    'labels': message.get('labelIds', []),
                    'has_attachments': self._has_attachments(message),
                    'size_bytes': message.get('sizeEstimate', 0)
                }
            })

        # Event 2: email_read (if not UNREAD label)
        if 'UNREAD' not in message.get('labelIds', []):
            events.append({
                'subject_id': subject_id,
                'event_type': 'email_read',
                'event_time': datetime.now(UTC).isoformat(),  # Approximate
                'payload': {
                    'message_id': message_id
                }
            })

        # Event 3: email_starred (if STARRED label)
        if 'STARRED' in message.get('labelIds', []):
            events.append({
                'subject_id': subject_id,
                'event_type': 'email_starred',
                'event_time': datetime.now(UTC).isoformat(),
                'payload': {
                    'message_id': message_id
                }
            })

        # Event 4: email_archived (if not in INBOX)
        if 'INBOX' not in message.get('labelIds', []):
            events.append({
                'subject_id': subject_id,
                'event_type': 'email_archived',
                'event_time': datetime.now(UTC).isoformat(),
                'payload': {
                    'message_id': message_id,
                    'labels': message.get('labelIds', [])
                }
            })

        return events

    def _build_query(self, since: datetime = None) -> str:
        """Build Gmail search query"""
        if since:
            # Gmail uses seconds since epoch
            timestamp = int(since.timestamp())
            return f"after:{timestamp}"
        return ""

    def _fetch_messages(self, user_email: str, query: str) -> List[str]:
        """Fetch message IDs from Gmail"""
        results = self.gmail.users().messages().list(
            userId='me',
            q=query,
            maxResults=500
        ).execute()

        return [msg['id'] for msg in results.get('messages', [])]

    def _parse_date(self, date_str: str) -> datetime:
        """Parse email date header"""
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)

    def _has_attachments(self, message: dict) -> bool:
        """Check if message has attachments"""
        if 'parts' in message.get('payload', {}):
            for part in message['payload']['parts']:
                if part.get('filename'):
                    return True
        return False


class GmailWebhookHandler:
    """Handle Gmail push notifications"""

    async def handle_notification(self, notification: dict):
        """
        Handle incoming Gmail push notification.

        Notification format:
        {
            "message": {
                "data": "base64-encoded-data",
                "messageId": "1234567890",
                "publishTime": "2025-12-17T10:00:00.000Z"
            }
        }
        """
        import base64
        import json

        # Decode notification
        data = base64.b64decode(notification['message']['data']).decode('utf-8')
        payload = json.loads(data)

        # Extract email address and history ID
        email_address = payload['emailAddress']
        history_id = payload['historyId']

        # Fetch changes since last sync
        sync_service = GmailSyncService(...)
        await sync_service.sync_incremental(email_address, history_id)
```

---

## Workflow Examples for Email

### 1. Auto-Archive Old Emails
```json
{
  "name": "Archive emails older than 30 days",
  "trigger_event_type": "email_received",
  "trigger_conditions": null,
  "actions": [{
    "type": "create_event",
    "params": {
      "event_type": "email_archived",
      "payload": {
        "message_id": "{{ payload.message_id }}",
        "archived_at": "{{ now() }}",
        "reason": "auto_archive_30d"
      }
    }
  }],
  "max_executions_per_day": 1000
}
```

### 2. Label Important Senders
```json
{
  "name": "Label emails from VIPs",
  "trigger_event_type": "email_received",
  "trigger_conditions": {
    "payload.from": "boss@company.com"
  },
  "actions": [{
    "type": "create_event",
    "params": {
      "event_type": "label_added",
      "payload": {
        "message_id": "{{ payload.message_id }}",
        "label": "VIP",
        "added_at": "{{ now() }}"
      }
    }
  }]
}
```

### 3. Response Time Tracking
```json
{
  "name": "Track response to important emails",
  "trigger_event_type": "email_sent",
  "trigger_conditions": null,
  "actions": [{
    "type": "create_event",
    "params": {
      "event_type": "response_sent",
      "payload": {
        "thread_id": "{{ payload.thread_id }}",
        "response_time_minutes": "{{ calculate_response_time() }}"
      }
    }
  }]
}
```

---

## Query Patterns

### Current Email State (No Projection Model)
```python
# Query using events directly
async def get_unread_count(subject_id: str) -> int:
    """Get unread email count by querying events"""
    # Get all received emails
    received = await event_repo.get_by_type(
        tenant_id,
        event_type='email_received'
    )
    received_ids = {e.payload['message_id'] for e in received}

    # Get all read emails
    read = await event_repo.get_by_type(
        tenant_id,
        event_type='email_read'
    )
    read_ids = {e.payload['message_id'] for e in read}

    # Unread = received - read
    return len(received_ids - read_ids)
```

### With Projection Model (Faster)
```python
async def get_unread_count_fast(subject_id: str) -> int:
    """Get unread count from projection (pre-computed)"""
    projection = await db.get(EmailAccountProjection, subject_id)
    return projection.unread_count if projection else 0
```

---

## API Usage Examples

### Setup Email Account
```bash
# 1. Create subject for email account
POST /subjects/
{
  "subject_type": "email_account",
  "external_ref": "user@gmail.com"
}

# Response: {"id": "subj_abc123", ...}

# 2. Create email schemas
POST /event-schemas/
{
  "event_type": "email_received",
  "version": 1,
  "schema_definition": { ... }
}
```

### Sync Emails
```bash
# Run sync script
python integrations/gmail/sync_mailbox.py \
  --email user@gmail.com \
  --subject-id subj_abc123 \
  --since "2025-01-01T00:00:00Z"
```

### Query Timeline
```bash
# Get email timeline
GET /events/subject/subj_abc123?limit=100

# Response:
[
  {
    "id": "evt_001",
    "event_type": "email_received",
    "event_time": "2025-12-17T10:00:00Z",
    "payload": {
      "from": "friend@example.com",
      "subject": "Lunch tomorrow?",
      ...
    }
  },
  {
    "id": "evt_002",
    "event_type": "email_read",
    "event_time": "2025-12-17T10:05:00Z",
    "payload": {
      "message_id": "msg_001"
    }
  }
]
```

---

## Deployment Architecture

```
┌─────────────────┐
│   Gmail API     │
│  (Push Notify)  │
└────────┬────────┘
         │
         ↓
┌─────────────────────────────┐
│  Integration Service        │
│  - Gmail Sync               │
│  - Webhook Handler          │
│  - Event Transformation     │
└────────┬────────────────────┘
         │
         ↓ HTTP POST /events/
┌─────────────────────────────┐
│   Timeline API              │
│   - Event Storage           │
│   - Chain Verification      │
│   - Workflow Execution      │
└────────┬────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│   PostgreSQL                │
│   - Events (immutable)      │
│   - Projections (optional)  │
└─────────────────────────────┘
```

---

## Summary: No New Core Models Needed

### ✅ Use Existing Models
- **Subject** → email account (via subject_type configuration)
- **Event** → email activities (configured via event_type)
- **EventSchema** → email payload validation
- **Workflow** → email automation rules

### ⚠️ Optional Performance Models
- **EmailAccountProjection** → pre-computed aggregates (optional)
- **Materialized Views** → fast queries (optional)

### 🔧 New Code Required
- **Integration Service** → Gmail API sync
- **Webhook Handler** → real-time updates
- **Projection Builder** → rebuild aggregates (if using projections)

**Timeline Philosophy**: Generic models + configuration = domain flexibility
