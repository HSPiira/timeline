# Universal Email Integration - Multi-Provider Design

## Architecture Philosophy

**Provider Abstraction**: Single Timeline integration, multiple email providers

```
Timeline Events (universal)
    ↑
Universal Email Sync Service
    ↑
Provider Protocol (interface)
    ↑
├── GmailProvider
├── OutlookProvider
├── IMAPProvider (works with iCloud, Yahoo, custom servers)
├── Exchange/Office365Provider
└── Future providers...
```

---

## Core Abstraction Layer

### Email Provider Protocol

```python
# integrations/email/protocols.py
from typing import Protocol, List, Optional, AsyncIterator
from datetime import datetime
from dataclasses import dataclass

@dataclass
class EmailMessage:
    """Universal email message structure (provider-agnostic)"""
    message_id: str
    thread_id: Optional[str]
    from_address: str
    to_addresses: List[str]
    cc_addresses: List[str]
    bcc_addresses: List[str]
    subject: str
    timestamp: datetime
    labels: List[str]
    is_read: bool
    is_starred: bool
    is_archived: bool
    has_attachments: bool
    size_bytes: int
    raw_headers: dict  # Provider-specific headers
    provider_metadata: dict  # Provider-specific data


@dataclass
class EmailProviderConfig:
    """Configuration for email provider connection"""
    provider_type: str  # "gmail", "outlook", "imap", "exchange"
    user_email: str
    credentials: dict  # Provider-specific credentials
    connection_params: dict  # Provider-specific params


class IEmailProvider(Protocol):
    """
    Universal email provider interface.
    All email providers must implement this protocol.
    """

    async def connect(self, config: EmailProviderConfig) -> None:
        """Establish connection to email provider"""
        ...

    async def disconnect(self) -> None:
        """Close connection"""
        ...

    async def fetch_messages(
        self,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[EmailMessage]:
        """Fetch messages from mailbox"""
        ...

    async def fetch_messages_stream(
        self,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None
    ) -> AsyncIterator[EmailMessage]:
        """Stream messages (for large mailboxes)"""
        ...

    async def get_message(self, message_id: str) -> Optional[EmailMessage]:
        """Fetch single message by ID"""
        ...

    async def setup_webhook(self, callback_url: str) -> dict:
        """Setup push notifications (if supported)"""
        ...

    async def remove_webhook(self) -> None:
        """Remove push notifications"""
        ...

    @property
    def supports_webhooks(self) -> bool:
        """Whether this provider supports webhooks"""
        ...

    @property
    def supports_labels(self) -> bool:
        """Whether this provider supports labels/folders"""
        ...
```

---

## Concrete Provider Implementations

### 1. Gmail Provider

```python
# integrations/email/providers/gmail_provider.py
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from integrations.email.protocols import IEmailProvider, EmailMessage, EmailProviderConfig
from typing import List, Optional, AsyncIterator
from datetime import datetime

class GmailProvider:
    """Gmail API implementation"""

    def __init__(self):
        self.service = None
        self.config = None

    async def connect(self, config: EmailProviderConfig) -> None:
        """Connect to Gmail API"""
        credentials = Credentials(**config.credentials)
        self.service = build('gmail', 'v1', credentials=credentials)
        self.config = config

    async def disconnect(self) -> None:
        """Gmail API is stateless, no cleanup needed"""
        self.service = None

    async def fetch_messages(
        self,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[EmailMessage]:
        """Fetch messages from Gmail"""
        query = self._build_query(since, labels)

        results = self.service.users().messages().list(
            userId='me',
            q=query,
            maxResults=limit
        ).execute()

        messages = []
        for msg_ref in results.get('messages', []):
            msg = await self.get_message(msg_ref['id'])
            if msg:
                messages.append(msg)

        return messages

    async def fetch_messages_stream(
        self,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None
    ) -> AsyncIterator[EmailMessage]:
        """Stream messages from Gmail"""
        query = self._build_query(since, labels)
        page_token = None

        while True:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=500,
                pageToken=page_token
            ).execute()

            for msg_ref in results.get('messages', []):
                msg = await self.get_message(msg_ref['id'])
                if msg:
                    yield msg

            page_token = results.get('nextPageToken')
            if not page_token:
                break

    async def get_message(self, message_id: str) -> Optional[EmailMessage]:
        """Fetch single Gmail message and convert to universal format"""
        msg = self.service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in msg['payload']['headers']}

        return EmailMessage(
            message_id=msg['id'],
            thread_id=msg.get('threadId'),
            from_address=headers.get('From', ''),
            to_addresses=self._parse_addresses(headers.get('To', '')),
            cc_addresses=self._parse_addresses(headers.get('Cc', '')),
            bcc_addresses=self._parse_addresses(headers.get('Bcc', '')),
            subject=headers.get('Subject', ''),
            timestamp=self._parse_date(headers.get('Date')),
            labels=msg.get('labelIds', []),
            is_read='UNREAD' not in msg.get('labelIds', []),
            is_starred='STARRED' in msg.get('labelIds', []),
            is_archived='INBOX' not in msg.get('labelIds', []),
            has_attachments=self._has_attachments(msg),
            size_bytes=msg.get('sizeEstimate', 0),
            raw_headers=headers,
            provider_metadata={
                'gmail_label_ids': msg.get('labelIds', []),
                'gmail_internal_date': msg.get('internalDate')
            }
        )

    async def setup_webhook(self, callback_url: str) -> dict:
        """Setup Gmail push notifications"""
        topic_name = f"projects/{self.config.connection_params['project_id']}/topics/gmail-push"

        watch_request = {
            'topicName': topic_name,
            'labelIds': ['INBOX']
        }

        result = self.service.users().watch(
            userId='me',
            body=watch_request
        ).execute()

        return {
            'history_id': result['historyId'],
            'expiration': result['expiration']
        }

    async def remove_webhook(self) -> None:
        """Stop Gmail push notifications"""
        self.service.users().stop(userId='me').execute()

    @property
    def supports_webhooks(self) -> bool:
        return True

    @property
    def supports_labels(self) -> bool:
        return True

    def _build_query(self, since: Optional[datetime], labels: Optional[List[str]]) -> str:
        """Build Gmail search query"""
        parts = []
        if since:
            timestamp = int(since.timestamp())
            parts.append(f"after:{timestamp}")
        if labels:
            for label in labels:
                parts.append(f"label:{label}")
        return " ".join(parts)

    def _parse_addresses(self, address_str: str) -> List[str]:
        """Parse comma-separated email addresses"""
        if not address_str:
            return []
        return [addr.strip() for addr in address_str.split(',')]

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
```

### 2. IMAP Provider (Works with iCloud, Yahoo, Custom Servers)

```python
# integrations/email/providers/imap_provider.py
import aioimaplib
import email
from email.utils import parsedate_to_datetime
from integrations.email.protocols import IEmailProvider, EmailMessage, EmailProviderConfig
from typing import List, Optional, AsyncIterator
from datetime import datetime

class IMAPProvider:
    """
    Universal IMAP provider.
    Works with: iCloud, Yahoo, Gmail (IMAP), custom IMAP servers
    """

    def __init__(self):
        self.client = None
        self.config = None

    async def connect(self, config: EmailProviderConfig) -> None:
        """Connect to IMAP server"""
        host = config.connection_params['imap_host']
        port = config.connection_params.get('imap_port', 993)

        self.client = aioimaplib.IMAP4_SSL(host=host, port=port)

        username = config.credentials['username']
        password = config.credentials['password']

        await self.client.wait_hello_from_server()
        await self.client.login(username, password)

        self.config = config

    async def disconnect(self) -> None:
        """Close IMAP connection"""
        if self.client:
            await self.client.logout()
            self.client = None

    async def fetch_messages(
        self,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[EmailMessage]:
        """Fetch messages via IMAP"""
        folder = labels[0] if labels else 'INBOX'
        await self.client.select(folder)

        # Build IMAP search criteria
        search_criteria = self._build_search_criteria(since)

        _, msg_nums = await self.client.search('UTF-8', search_criteria)
        msg_nums = msg_nums[0].split()[-limit:]  # Get last N messages

        messages = []
        for num in msg_nums:
            msg = await self.get_message(num.decode())
            if msg:
                messages.append(msg)

        return messages

    async def fetch_messages_stream(
        self,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None
    ) -> AsyncIterator[EmailMessage]:
        """Stream messages via IMAP"""
        folder = labels[0] if labels else 'INBOX'
        await self.client.select(folder)

        search_criteria = self._build_search_criteria(since)
        _, msg_nums = await self.client.search('UTF-8', search_criteria)

        for num in msg_nums[0].split():
            msg = await self.get_message(num.decode())
            if msg:
                yield msg

    async def get_message(self, message_id: str) -> Optional[EmailMessage]:
        """Fetch single message via IMAP"""
        _, msg_data = await self.client.fetch(message_id, '(RFC822 FLAGS)')

        if not msg_data or not msg_data[1]:
            return None

        # Parse email
        email_body = msg_data[1]
        email_message = email.message_from_bytes(email_body)

        # Parse flags
        flags_match = msg_data[0].decode()
        is_read = '\\Seen' in flags_match
        is_starred = '\\Flagged' in flags_match

        return EmailMessage(
            message_id=email_message.get('Message-ID', message_id),
            thread_id=email_message.get('In-Reply-To'),  # Approximate threading
            from_address=email_message.get('From', ''),
            to_addresses=self._parse_addresses(email_message.get('To', '')),
            cc_addresses=self._parse_addresses(email_message.get('Cc', '')),
            bcc_addresses=self._parse_addresses(email_message.get('Bcc', '')),
            subject=email_message.get('Subject', ''),
            timestamp=parsedate_to_datetime(email_message.get('Date')),
            labels=[],  # IMAP doesn't have labels, use folders instead
            is_read=is_read,
            is_starred=is_starred,
            is_archived=False,  # IMAP doesn't have archive concept
            has_attachments=self._has_attachments(email_message),
            size_bytes=len(email_body),
            raw_headers=dict(email_message.items()),
            provider_metadata={
                'imap_uid': message_id,
                'imap_flags': flags_match
            }
        )

    async def setup_webhook(self, callback_url: str) -> dict:
        """IMAP doesn't support webhooks"""
        raise NotImplementedError("IMAP doesn't support push notifications")

    async def remove_webhook(self) -> None:
        """IMAP doesn't support webhooks"""
        pass

    @property
    def supports_webhooks(self) -> bool:
        return False

    @property
    def supports_labels(self) -> bool:
        return False  # IMAP uses folders, not labels

    def _build_search_criteria(self, since: Optional[datetime]) -> str:
        """Build IMAP search criteria"""
        if since:
            date_str = since.strftime('%d-%b-%Y')
            return f'SINCE {date_str}'
        return 'ALL'

    def _parse_addresses(self, address_str: str) -> List[str]:
        """Parse comma-separated email addresses"""
        if not address_str:
            return []
        return [addr.strip() for addr in address_str.split(',')]

    def _has_attachments(self, email_message) -> bool:
        """Check if email has attachments"""
        for part in email_message.walk():
            if part.get_content_disposition() == 'attachment':
                return True
        return False
```

### 3. Outlook/Office365 Provider

```python
# integrations/email/providers/outlook_provider.py
from O365 import Account
from integrations.email.protocols import IEmailProvider, EmailMessage, EmailProviderConfig
from typing import List, Optional, AsyncIterator
from datetime import datetime

class OutlookProvider:
    """
    Microsoft Outlook/Office365 provider.
    Uses Microsoft Graph API.
    """

    def __init__(self):
        self.account = None
        self.mailbox = None
        self.config = None

    async def connect(self, config: EmailProviderConfig) -> None:
        """Connect to Microsoft Graph API"""
        credentials = (
            config.credentials['client_id'],
            config.credentials['client_secret']
        )

        self.account = Account(credentials)

        if not self.account.is_authenticated:
            # OAuth flow
            self.account.authenticate(
                scopes=['https://graph.microsoft.com/Mail.Read']
            )

        self.mailbox = self.account.mailbox()
        self.config = config

    async def disconnect(self) -> None:
        """Microsoft Graph API is stateless"""
        self.account = None
        self.mailbox = None

    async def fetch_messages(
        self,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[EmailMessage]:
        """Fetch messages from Outlook"""
        query = self.mailbox.inbox_folder().get_messages(limit=limit)

        if since:
            query = query.filter(f"receivedDateTime ge {since.isoformat()}")

        messages = []
        for msg in query:
            messages.append(self._convert_message(msg))

        return messages

    async def fetch_messages_stream(
        self,
        since: Optional[datetime] = None,
        labels: Optional[List[str]] = None
    ) -> AsyncIterator[EmailMessage]:
        """Stream messages from Outlook"""
        query = self.mailbox.inbox_folder().get_messages()

        if since:
            query = query.filter(f"receivedDateTime ge {since.isoformat()}")

        for msg in query:
            yield self._convert_message(msg)

    async def get_message(self, message_id: str) -> Optional[EmailMessage]:
        """Fetch single message from Outlook"""
        msg = self.mailbox.get_message(object_id=message_id)
        return self._convert_message(msg) if msg else None

    def _convert_message(self, msg) -> EmailMessage:
        """Convert Outlook message to universal format"""
        return EmailMessage(
            message_id=msg.object_id,
            thread_id=msg.conversation_id,
            from_address=msg.sender.address,
            to_addresses=[r.address for r in msg.to.recipients],
            cc_addresses=[r.address for r in msg.cc.recipients],
            bcc_addresses=[r.address for r in msg.bcc.recipients],
            subject=msg.subject or '',
            timestamp=msg.received,
            labels=msg.categories or [],
            is_read=msg.is_read,
            is_starred=msg.flag.flagged,
            is_archived=False,  # Outlook doesn't have archive
            has_attachments=msg.has_attachments,
            size_bytes=0,  # Not directly available in Graph API
            raw_headers={},
            provider_metadata={
                'outlook_conversation_id': msg.conversation_id,
                'outlook_importance': msg.importance
            }
        )

    async def setup_webhook(self, callback_url: str) -> dict:
        """Setup Microsoft Graph webhooks (subscriptions)"""
        subscription = self.account.create_subscription(
            resource='/me/mailFolderMessages',
            notification_url=callback_url,
            change_type='created,updated',
            expiration_minutes=4230  # Max 3 days
        )

        return {
            'subscription_id': subscription['id'],
            'expiration': subscription['expirationDateTime']
        }

    async def remove_webhook(self) -> None:
        """Remove Microsoft Graph webhook"""
        # Implementation depends on storing subscription ID
        pass

    @property
    def supports_webhooks(self) -> bool:
        return True

    @property
    def supports_labels(self) -> bool:
        return True  # Outlook uses categories
```

---

## Provider Factory & Configuration

### Provider Factory

```python
# integrations/email/factory.py
from integrations.email.protocols import IEmailProvider, EmailProviderConfig
from integrations.email.providers.gmail_provider import GmailProvider
from integrations.email.providers.imap_provider import IMAPProvider
from integrations.email.providers.outlook_provider import OutlookProvider

class EmailProviderFactory:
    """Factory for creating email provider instances"""

    _providers = {
        'gmail': GmailProvider,
        'outlook': OutlookProvider,
        'office365': OutlookProvider,
        'imap': IMAPProvider,
        'icloud': IMAPProvider,  # iCloud uses IMAP
        'yahoo': IMAPProvider,   # Yahoo uses IMAP
    }

    @classmethod
    def create_provider(cls, config: EmailProviderConfig) -> IEmailProvider:
        """Create email provider instance"""
        provider_class = cls._providers.get(config.provider_type.lower())

        if not provider_class:
            raise ValueError(f"Unknown provider type: {config.provider_type}")

        return provider_class()

    @classmethod
    def register_provider(cls, provider_type: str, provider_class: type):
        """Register custom email provider"""
        cls._providers[provider_type.lower()] = provider_class
```

### Configuration Storage

```python
# models/email_account.py
from sqlalchemy import Column, String, JSON, ForeignKey, DateTime, Boolean
from sqlalchemy.sql import func
from core.database import Base
from utils.generators import generate_cuid

class EmailAccount(Base):
    """
    Email account configuration and credentials.
    NOT a core Timeline model - this is integration metadata.
    """
    __tablename__ = "email_account"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(String, ForeignKey("subject.id", ondelete="CASCADE"), nullable=False)

    # Provider configuration
    provider_type = Column(String, nullable=False)  # gmail, outlook, imap, etc.
    email_address = Column(String, nullable=False)

    # Encrypted credentials (use Fernet encryption)
    credentials_encrypted = Column(String, nullable=False)

    # Provider-specific connection params (non-sensitive)
    connection_params = Column(JSON, nullable=True)

    # Sync metadata
    last_sync_at = Column(DateTime(timezone=True))
    last_sync_history_id = Column(String)  # Provider-specific sync cursor
    webhook_active = Column(Boolean, default=False)
    webhook_metadata = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

### Credential Encryption

```python
# integrations/email/crypto.py
from cryptography.fernet import Fernet
from core.config import get_settings
import json

class CredentialEncryptor:
    """Encrypt/decrypt email credentials"""

    def __init__(self):
        settings = get_settings()
        # Store encryption key in environment variable
        self.cipher = Fernet(settings.encryption_key.encode())

    def encrypt(self, credentials: dict) -> str:
        """Encrypt credentials dictionary"""
        json_str = json.dumps(credentials)
        encrypted = self.cipher.encrypt(json_str.encode())
        return encrypted.decode()

    def decrypt(self, encrypted: str) -> dict:
        """Decrypt credentials"""
        decrypted = self.cipher.decrypt(encrypted.encode())
        return json.loads(decrypted.decode())
```

---

## Universal Sync Service

```python
# integrations/email/universal_sync.py
from integrations.email.protocols import IEmailProvider, EmailMessage, EmailProviderConfig
from integrations.email.factory import EmailProviderFactory
from integrations.email.crypto import CredentialEncryptor
from models.email_account import EmailAccount
from typing import List
from datetime import datetime
import httpx

class UniversalEmailSync:
    """
    Provider-agnostic email sync service.
    Works with ANY email provider.
    """

    def __init__(self, timeline_api_url: str, timeline_api_token: str):
        self.timeline_api = httpx.AsyncClient(
            base_url=timeline_api_url,
            headers={'Authorization': f'Bearer {timeline_api_token}'}
        )
        self.encryptor = CredentialEncryptor()

    async def sync_account(
        self,
        email_account: EmailAccount,
        incremental: bool = True
    ) -> dict:
        """
        Sync email account (works with ANY provider).

        Args:
            email_account: EmailAccount configuration
            incremental: Only sync new emails since last sync

        Returns:
            Sync statistics
        """
        # 1. Build provider config
        credentials = self.encryptor.decrypt(email_account.credentials_encrypted)

        config = EmailProviderConfig(
            provider_type=email_account.provider_type,
            user_email=email_account.email_address,
            credentials=credentials,
            connection_params=email_account.connection_params or {}
        )

        # 2. Create provider (Gmail, Outlook, IMAP, etc.)
        provider = EmailProviderFactory.create_provider(config)

        stats = {
            'provider': email_account.provider_type,
            'emails_fetched': 0,
            'events_created': 0,
            'errors': []
        }

        try:
            # 3. Connect to provider
            await provider.connect(config)

            # 4. Fetch messages
            since = email_account.last_sync_at if incremental else None

            if provider.supports_webhooks:
                # Use incremental sync if available
                messages = await provider.fetch_messages(since=since, limit=500)
            else:
                # Full sync or use date filter
                messages = await provider.fetch_messages(since=since, limit=1000)

            stats['emails_fetched'] = len(messages)

            # 5. Transform to Timeline events (UNIVERSAL)
            for message in messages:
                try:
                    events = self._transform_message_to_events(
                        message, email_account.subject_id
                    )

                    # 6. Create Timeline events
                    for event in events:
                        await self.timeline_api.post('/events/', json=event)
                        stats['events_created'] += 1

                except Exception as e:
                    stats['errors'].append({
                        'message_id': message.message_id,
                        'error': str(e)
                    })

            # 7. Update sync metadata
            email_account.last_sync_at = datetime.now(UTC)
            # Save to database

        finally:
            await provider.disconnect()

        return stats

    def _transform_message_to_events(
        self,
        message: EmailMessage,
        subject_id: str
    ) -> List[dict]:
        """
        Transform universal EmailMessage to Timeline events.
        SAME LOGIC FOR ALL PROVIDERS.
        """
        events = []

        # Determine if sent or received
        is_sent = message.from_address == message.provider_metadata.get('user_email')

        # Event 1: email_received or email_sent
        event_type = 'email_sent' if is_sent else 'email_received'

        events.append({
            'subject_id': subject_id,
            'event_type': event_type,
            'event_time': message.timestamp.isoformat(),
            'payload': {
                'message_id': message.message_id,
                'thread_id': message.thread_id,
                'from': message.from_address,
                'to': message.to_addresses,
                'cc': message.cc_addresses,
                'subject': message.subject,
                'timestamp': message.timestamp.isoformat(),
                'labels': message.labels,
                'has_attachments': message.has_attachments,
                'size_bytes': message.size_bytes,
                'provider': message.provider_metadata
            }
        })

        # Event 2: email_read
        if message.is_read:
            events.append({
                'subject_id': subject_id,
                'event_type': 'email_read',
                'event_time': message.timestamp.isoformat(),  # Approximate
                'payload': {
                    'message_id': message.message_id
                }
            })

        # Event 3: email_starred
        if message.is_starred:
            events.append({
                'subject_id': subject_id,
                'event_type': 'email_starred',
                'event_time': message.timestamp.isoformat(),
                'payload': {
                    'message_id': message.message_id
                }
            })

        # Event 4: email_archived
        if message.is_archived:
            events.append({
                'subject_id': subject_id,
                'event_type': 'email_archived',
                'event_time': message.timestamp.isoformat(),
                'payload': {
                    'message_id': message.message_id,
                    'labels': message.labels
                }
            })

        return events
```

---

## Usage Examples

### Setup Different Providers

```python
# Gmail Account
gmail_account = EmailAccount(
    tenant_id="tenant_123",
    subject_id="subj_gmail",
    provider_type="gmail",
    email_address="user@gmail.com",
    credentials_encrypted=encrypt({
        "access_token": "...",
        "refresh_token": "...",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "...",
        "client_secret": "..."
    }),
    connection_params={
        "project_id": "my-project"
    }
)

# iCloud Account (via IMAP)
icloud_account = EmailAccount(
    tenant_id="tenant_123",
    subject_id="subj_icloud",
    provider_type="imap",
    email_address="user@icloud.com",
    credentials_encrypted=encrypt({
        "username": "user@icloud.com",
        "password": "app-specific-password"
    }),
    connection_params={
        "imap_host": "imap.mail.me.com",
        "imap_port": 993
    }
)

# Outlook Account
outlook_account = EmailAccount(
    tenant_id="tenant_123",
    subject_id="subj_outlook",
    provider_type="outlook",
    email_address="user@outlook.com",
    credentials_encrypted=encrypt({
        "client_id": "...",
        "client_secret": "...",
        "access_token": "..."
    }),
    connection_params={}
)
```

### Sync Any Provider

```python
# SAME CODE works for Gmail, Outlook, iCloud, Yahoo, etc.
sync = UniversalEmailSync(
    timeline_api_url="http://localhost:8000",
    timeline_api_token="jwt_token_here"
)

# Sync Gmail
stats = await sync.sync_account(gmail_account)
print(f"Gmail: {stats['events_created']} events created")

# Sync iCloud (same code!)
stats = await sync.sync_account(icloud_account)
print(f"iCloud: {stats['events_created']} events created")

# Sync Outlook (same code!)
stats = await sync.sync_account(outlook_account)
print(f"Outlook: {stats['events_created']} events created")
```

---

## Benefits of This Design

### 1. Provider Agnostic
- **One sync service** works with all providers
- **Same Timeline events** regardless of source
- **Easy to add new providers** (just implement protocol)

### 2. Separation of Concerns
- **Timeline** = domain logic (events, subjects)
- **EmailAccount** = integration metadata (credentials, sync state)
- **Providers** = external system adapters

### 3. Security
- Credentials encrypted at rest
- Provider-specific auth (OAuth, app passwords, etc.)
- Never expose credentials in Timeline events

### 4. Flexibility
- Mix multiple providers for same user
- Different sync strategies per provider
- Easy testing (mock providers)

---

## Summary

```
┌─────────────────────────────────────┐
│ Timeline Core (unchanged)           │
│ - Subject (email_account)           │
│ - Event (email_received, etc.)      │
│ - EventSchema                       │
└──────────────┬──────────────────────┘
               ↑
┌──────────────┴──────────────────────┐
│ Universal Email Sync                │
│ - Provider-agnostic transformation  │
│ - Timeline event creation           │
└──────────────┬──────────────────────┘
               ↑
┌──────────────┴──────────────────────┐
│ Email Provider Protocol (interface) │
└──────────────┬──────────────────────┘
               ↑
┌──────┬───────┴─────┬────────┬───────┐
│Gmail │ Outlook     │ IMAP   │ More  │
│      │ /Office365  │(iCloud,│       │
│      │             │ Yahoo) │       │
└──────┴─────────────┴────────┴───────┘
```

**Key**: You add NEW providers without changing Timeline or sync logic! 🎯

Want me to create a working prototype of this multi-provider system?
