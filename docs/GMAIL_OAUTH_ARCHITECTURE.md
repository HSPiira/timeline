# Gmail OAuth Architecture Guide

Complete guide for understanding and implementing Gmail OAuth in a multi-tenant environment.

---

## Architecture Overview

### Current Design: Per-User Self-Service OAuth ✅

```
Timeline Multi-Tenant System
├── Tenant A (Company A)
│   ├── User 1 → Connects their Gmail (user1@company.com)
│   ├── User 2 → Connects their Gmail (user2@company.com)
│   └── User 3 → Connects their Gmail (user3@company.com)
│
└── Tenant B (Company B)
    ├── User 4 → Connects their Gmail (user4@othercompany.com)
    └── User 5 → Connects their Gmail (user5@othercompany.com)
```

**Key Points:**
- Each user authorizes their own Gmail account
- Credentials stored encrypted per email account
- Email events belong to the tenant (team visibility)
- Users can only sync their own authorized accounts

---

## User Flow (Self-Service)

### For End Users

**Step 1: User Wants to Connect Gmail**

```
User Interface:
┌────────────────────────────────┐
│  Email Accounts                │
│                                │
│  ┌──────────────────────────┐ │
│  │ + Connect Gmail Account  │ │  ← User clicks
│  └──────────────────────────┘ │
└────────────────────────────────┘
```

**Step 2: Frontend Initiates OAuth**

```javascript
// Frontend: Initiate Gmail OAuth
async function connectGmail() {
  // 1. Call authorize endpoint
  const response = await fetch('/auth/gmail/authorize', {
    headers: {
      'Authorization': `Bearer ${userToken}`  // User's Timeline auth token
    }
  });

  const data = await response.json();

  // 2. Open Google OAuth in popup or redirect
  window.location.href = data.auth_url;
  // OR for better UX:
  // window.open(data.auth_url, 'gmail-auth', 'width=600,height=700');
}
```

**Step 3: User Authorizes on Google**

```
Google OAuth Consent Screen:
┌─────────────────────────────────┐
│  Timeline wants to access:      │
│  ✓ Read your Gmail messages     │
│  ✓ Modify your Gmail labels     │
│                                 │
│  [ Cancel ]    [ Allow ]        │
└─────────────────────────────────┘
```

**Step 4: Callback Saves Account**

```
Google → /auth/gmail/callback → Timeline saves:
- Email address
- Encrypted tokens
- Links to user's tenant
- Creates Subject for email account
```

**Step 5: User Can Sync**

```
User sees their connected Gmail:
┌────────────────────────────────┐
│  Connected Accounts            │
│                                │
│  ✓ user@company.com            │
│    Last sync: 2 mins ago       │
│    [ Sync Now ]  [ Disconnect ]│
└────────────────────────────────┘
```

---

## Authentication Setup

### One-Time Google Cloud Setup (Admin/Developer)

This is done **once** by the system administrator:

```bash
# 1. Create Google Cloud Project
# 2. Enable Gmail API
# 3. Create OAuth Client
# 4. Configure in .env

GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-your-client-secret
GMAIL_REDIRECT_URI=https://yourdomain.com/auth/gmail/callback
```

**Important:**
- These credentials are **shared** across all users
- But each user authorizes their own Gmail account
- Tokens are **per-user**, not shared

### How Google OAuth Works

```
Your System (Timeline)
├── OAuth Client ID: abc123.apps.googleusercontent.com
│   └── Used by ALL users to initiate OAuth
│
User 1 Authorization
├── Authorizes: user1@gmail.com
├── Receives: Access Token + Refresh Token (specific to user1)
└── Stored: Encrypted in database (only for user1)

User 2 Authorization
├── Authorizes: user2@gmail.com
├── Receives: Access Token + Refresh Token (specific to user2)
└── Stored: Encrypted in database (only for user2)
```

**Same OAuth Client, Different User Tokens** ✅

---

## Database Schema

### How Email Accounts are Stored

```sql
-- email_account table
CREATE TABLE email_account (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,           -- Which tenant/company
    subject_id VARCHAR NOT NULL,          -- Timeline subject (for events)

    provider_type VARCHAR NOT NULL,       -- 'gmail'
    email_address VARCHAR NOT NULL,       -- user@gmail.com

    credentials_encrypted VARCHAR NOT NULL, -- Encrypted tokens (per user!)

    is_active BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMP,

    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Index for user's email accounts
CREATE INDEX idx_email_account_tenant
ON email_account(tenant_id);
```

### Current Limitation & Fix

**Current:** One email account per email address per tenant

**Problem:** What if multiple users in same tenant want to track the same shared inbox?

**Solution:** Add ownership tracking

```sql
-- Migration: Add ownership tracking
ALTER TABLE email_account
ADD COLUMN created_by VARCHAR REFERENCES "user"(id);

-- Now you can track who connected each account
-- AND allow same email for different users/purposes
```

---

## Security & Privacy

### Token Storage

```python
# How tokens are stored (automatically)
{
    "access_token": "ya29.a0Af...",     # Expires every 1 hour
    "refresh_token": "1//0gZ...",       # Permanent (until revoked)
    "client_id": "...",                 # Your app's client ID
    "client_secret": "..."              # Your app's secret
}
↓ Encrypted with Fernet
↓ Stored in database
"gAAAAABh3K2j..."  # Encrypted blob
```

**Security Benefits:**
- Each user's tokens are separate
- Encrypted at rest
- Can't access other users' emails
- Revocable by user at any time

### Access Control

```python
# Users can ONLY access their tenant's email accounts
@router.get("/")
async def list_email_accounts(
    tenant: Annotated[Tenant, Depends(get_current_tenant)]
):
    # Automatically filtered by tenant_id
    accounts = await db.execute(
        select(EmailAccount)
        .where(EmailAccount.tenant_id == tenant.id)
    )
    return accounts
```

---

## Multi-User Scenarios

### Scenario 1: Personal Gmail (Most Common)

```
User: Alice (alice@company.com)
Connects: alice@gmail.com

Result:
- Alice can sync her personal Gmail
- Events appear in Timeline for her tenant
- Only Alice's emails are synced
- Team can see Alice's email events (if permissions allow)
```

### Scenario 2: Shared Inbox

```
Team inbox: support@company.com

Option A (Current): One user connects
- User: Bob connects support@company.com
- All team members see events (via Timeline)
- Only Bob can trigger sync

Option B (Better): Add created_by field
- Multiple users can connect same inbox
- Each has their own OAuth tokens
- Any team member can trigger sync
```

### Scenario 3: Multiple Personal Accounts

```
User: Charlie
Connects:
- charlie@gmail.com (personal)
- charlie@company.com (work Gmail)
- charlie@freelance.com (side business)

Result:
- All three accounts appear in Timeline
- Charlie can sync all independently
- Events tagged by email address
- Team sees all events (filtered by permissions)
```

---

## Implementation: User Permissions

### Recommended: Add Permission Checks

```python
# Who can connect Gmail accounts?
PERMISSIONS = {
    "email_account:create": ["admin", "manager", "agent"],
    "email_account:sync": ["admin", "manager", "agent"],
    "email_account:delete": ["admin", "manager"],
}

# In endpoint
@router.post("/")
async def create_email_account(
    current_user: TokenPayload = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service)
):
    # Check permission
    if not await authz.has_permission(
        user_id=current_user.sub,
        tenant_id=current_user.tenant_id,
        permission="email_account:create"
    ):
        raise HTTPException(403, "Not authorized")

    # Proceed with OAuth...
```

---

## Frontend Integration

### React Example

```typescript
// EmailAccountsPage.tsx

import { useState } from 'react';

export function EmailAccountsPage() {
  const [accounts, setAccounts] = useState([]);

  // Connect Gmail
  async function connectGmail() {
    try {
      // 1. Get OAuth URL
      const response = await fetch('/auth/gmail/authorize', {
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });

      const { auth_url } = await response.json();

      // 2. Open OAuth in popup
      const popup = window.open(
        auth_url,
        'gmail-auth',
        'width=600,height=700'
      );

      // 3. Listen for callback
      window.addEventListener('message', (event) => {
        if (event.data.type === 'gmail-auth-success') {
          // Refresh account list
          loadAccounts();
          popup?.close();
        }
      });

    } catch (error) {
      console.error('OAuth failed:', error);
    }
  }

  // Sync in background
  async function syncAccount(accountId: string) {
    await fetch(`/email-accounts/${accountId}/sync-background`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ incremental: true })
    });

    // Show notification
    toast.success('Email sync started in background');
  }

  return (
    <div>
      <button onClick={connectGmail}>
        + Connect Gmail Account
      </button>

      {accounts.map(account => (
        <AccountCard
          key={account.id}
          account={account}
          onSync={() => syncAccount(account.id)}
        />
      ))}
    </div>
  );
}
```

### OAuth Callback Handler

```html
<!-- callback.html (redirect target) -->
<!DOCTYPE html>
<html>
<head>
    <title>Gmail Connected</title>
</head>
<body>
    <script>
        // Get URL parameters
        const params = new URLSearchParams(window.location.search);
        const code = params.get('code');
        const error = params.get('error');

        if (window.opener) {
            // Send message to parent window
            window.opener.postMessage({
                type: 'gmail-auth-success',
                code: code
            }, '*');
        } else {
            // Redirect back to app
            window.location.href = '/email-accounts?connected=true';
        }
    </script>

    <p>Gmail connected successfully! Closing window...</p>
</body>
</html>
```

---

## Admin vs. User OAuth

### Option 1: All Users Can Connect (Recommended)

**Pros:**
- Self-service (less admin work)
- Users control their own data
- Scales well
- Better security (no shared credentials)

**Cons:**
- Each user goes through OAuth
- More OAuth tokens to manage

**Best For:**
- SaaS products
- Team collaboration tools
- Personal productivity apps

### Option 2: Admin-Only OAuth

**Pros:**
- Centralized control
- Fewer OAuth flows
- Admin manages all accounts

**Cons:**
- Admin needs access to everyone's Gmail
- Privacy concerns
- Single point of failure
- Doesn't scale

**Best For:**
- Small teams
- Service accounts only
- Testing/development

---

## Recommended Configuration

### For Your Timeline System

**Use Case:** Multi-tenant SaaS for team timeline tracking

**Recommended Setup:**

```yaml
oauth_strategy: per_user_self_service

permissions:
  - role: admin
    can: [create, sync, delete, view_all]

  - role: manager
    can: [create, sync, delete, view_team]

  - role: agent
    can: [create, sync, view_own]

  - role: auditor
    can: [view_all]

features:
  - self_service_oauth: true
  - automatic_sync: true  # Background sync every 15 min
  - multiple_accounts_per_user: true
  - shared_inbox_support: true  # With created_by tracking
```

### Production Checklist

- [x] OAuth Client configured in Google Cloud
- [x] Environment variables set (.env)
- [x] Per-user OAuth flow implemented
- [x] Automatic token refresh working
- [x] Background sync available
- [ ] Add `created_by` field to track ownership (optional)
- [ ] Implement permission checks (optional)
- [ ] Add frontend OAuth popup flow
- [ ] Set up automatic scheduled sync (optional)
- [ ] Add OAuth status/monitoring

---

## FAQs

### Q: Do I need separate OAuth clients for each user?
**A:** No! One OAuth client serves all users. Each user gets their own tokens.

### Q: Can users revoke access?
**A:** Yes! Users can:
1. Revoke in Google Account settings
2. Delete email account in Timeline
3. Admin can deactivate account

### Q: What happens if token expires?
**A:** Automatic refresh! The system:
1. Detects expired token
2. Uses refresh token to get new access token
3. Saves new token to database
4. Continues sync

### Q: Can one user's emails be seen by another user in same tenant?
**A:** Depends on your permissions! By default:
- Email events are tenant-wide (team visibility)
- But you can add permission filters
- Email account credentials are per-user

### Q: How do I add admin-only OAuth?
**A:** Add permission check:
```python
if current_user.role not in ['admin', 'manager']:
    raise HTTPException(403, "Only admins can add email accounts")
```

---

## Next Steps

1. **Test the OAuth flow** - Connect your first Gmail account
2. **Set up background sync** - See BACKGROUND_EMAIL_SYNC.md
3. **Add permissions** - Control who can add accounts
4. **Build frontend** - Nice UI for connecting accounts
5. **Monitor usage** - Track OAuth errors and sync status

Your current architecture is already well-designed for per-user OAuth! 🎉
