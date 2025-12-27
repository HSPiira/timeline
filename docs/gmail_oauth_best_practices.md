# Gmail OAuth Best Practices - Preventing Token Expiration

## The Problem

Users should **never** need to re-authenticate if the system is properly designed. The current error (`Token has been expired or revoked`) indicates one of these issues:

1. **Refresh token never obtained** - OAuth flow didn't use `access_type='offline'`
2. **Refresh token not saved** - Token refresh callback isn't persisting changes
3. **Refresh token actually expired** - 6 months of non-use (rare with active sync)
4. **User manually revoked access** - In Google account settings

## The Solution

### 1. Proper OAuth Flow Configuration

**CRITICAL**: The initial OAuth authorization MUST include these parameters:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_config(
    client_config,
    scopes=['https://www.googleapis.com/auth/gmail.readonly']
)

# CRITICAL PARAMETERS:
credentials = flow.run_local_server(
    access_type='offline',  # Get refresh token that doesn't expire
    prompt='consent',       # Force consent to get NEW refresh token
    include_granted_scopes='true'  # Include previously granted scopes
)
```

**What each parameter does:**

- `access_type='offline'` - Tells Google to return a refresh token. Without this, you only get an access token that expires in 1 hour.
- `prompt='consent'` - Forces the consent screen even if user previously consented. This ensures you get a NEW refresh token (Google won't return refresh tokens on subsequent auth flows unless you force consent).
- `include_granted_scopes='true'` - Preserves previously granted permissions.

### 2. Token Lifecycle

```
Initial OAuth Flow:
┌─────────────────────────────────────────────────────────┐
│ User authorizes → Gets access_token + refresh_token     │
│ access_token: Valid for 1 hour                          │
│ refresh_token: Valid indefinitely (with exceptions)     │
└─────────────────────────────────────────────────────────┘

Token Usage:
┌─────────────────────────────────────────────────────────┐
│ 1. Use access_token for API calls                       │
│ 2. When access_token expires (1 hour):                  │
│    - Google OAuth library auto-uses refresh_token       │
│    - Gets new access_token (valid for 1 hour)           │
│    - Refresh_token remains the same                     │
│ 3. Save new access_token to database                    │
│ 4. Repeat indefinitely                                  │
└─────────────────────────────────────────────────────────┘

Refresh Token Expiration (rare):
┌─────────────────────────────────────────────────────────┐
│ Refresh tokens expire ONLY when:                        │
│ - User revokes access in Google account settings        │
│ - 6 months of complete non-use (no API calls at all)    │
│ - Google detects suspicious activity                    │
│ - User changes password (security policy)               │
└─────────────────────────────────────────────────────────┘
```

### 3. Implementation Checklist

#### ✅ OAuth Flow (Frontend/Initial Setup)

- [ ] Use `access_type='offline'` in OAuth flow
- [ ] Use `prompt='consent'` to ensure refresh token is returned
- [ ] Request minimal scopes: `https://www.googleapis.com/auth/gmail.readonly`
- [ ] Store BOTH access_token and refresh_token encrypted in database
- [ ] Include client_id and client_secret with credentials

#### ✅ Token Refresh (Backend/Sync Service)

- [x] Use Google's OAuth library (handles refresh automatically)
- [x] Implement token refresh callback to save new access tokens
- [x] Commit database transaction after successful sync (persists token updates)
- [x] Add proper error handling for RefreshError
- [x] Log token refresh events for monitoring

#### ✅ Error Handling

- [x] Catch `google.auth.exceptions.RefreshError`
- [x] Return 401 Unauthorized (not 500) when tokens invalid
- [x] Provide clear error message to user
- [ ] Implement notification system for token expiration
- [ ] Add admin dashboard to monitor token health

#### ✅ Monitoring & Maintenance

- [ ] Track last successful token refresh per account
- [ ] Alert when account hasn't synced in 5 months (before 6-month expiration)
- [ ] Log all token refresh events
- [ ] Dashboard showing token health status

### 4. Current Implementation Status

#### What's Working ✅

1. **Automatic token refresh** - Google's library handles this
2. **Token refresh callback** - Saves new access tokens to database
3. **Proper error handling** - Returns 401 instead of 500
4. **Transaction commit** - Persists token updates after sync

#### What Needs Fixing ⚠️

1. **Initial OAuth flow** - Need to ensure `access_type='offline'` is used
2. **Proactive monitoring** - Add token health dashboard
3. **User notifications** - Alert users before tokens expire
4. **Refresh token validation** - Check if refresh_token is actually present

### 5. Testing Token Refresh

Use the provided helper script:

```bash
# Validate existing credentials
python scripts/gmail_oauth_helper.py validate --credentials creds.json

# Generate new credentials with correct settings
python scripts/gmail_oauth_helper.py generate \
  --client-id YOUR_CLIENT_ID \
  --client-secret YOUR_CLIENT_SECRET \
  --output new_creds.json

# Test Gmail API access
python scripts/gmail_oauth_helper.py test --credentials new_creds.json
```

### 6. Database Schema Additions (Recommended)

Add these fields to track token health:

```python
class EmailAccount(Base):
    # ... existing fields ...

    # Token health monitoring
    token_last_refreshed_at = Column(DateTime, nullable=True)
    token_refresh_count = Column(Integer, default=0)
    token_refresh_failures = Column(Integer, default=0)
    last_auth_error = Column(String, nullable=True)
    last_auth_error_at = Column(DateTime, nullable=True)
```

### 7. Debugging Checklist

When a user reports "Token has expired or revoked":

1. **Check credentials in database**
   ```sql
   SELECT id, email_address, created_at, last_sync_at
   FROM email_account
   WHERE id = 'account_id';
   ```

2. **Decrypt and validate credentials**
   ```python
   from integrations.email.encryption import CredentialEncryptor
   encryptor = CredentialEncryptor()
   creds = encryptor.decrypt(account.credentials_encrypted)
   print(creds.keys())  # Should have: access_token, refresh_token, client_id, client_secret
   ```

3. **Test token refresh manually**
   ```python
   from google.oauth2.credentials import Credentials
   from google.auth.transport.requests import Request

   creds = Credentials(
       token=creds_dict['access_token'],
       refresh_token=creds_dict['refresh_token'],
       token_uri='https://oauth2.googleapis.com/token',
       client_id=creds_dict['client_id'],
       client_secret=creds_dict['client_secret']
   )

   try:
       creds.refresh(Request())
       print("✅ Token refresh works!")
   except Exception as e:
       print(f"❌ Token refresh failed: {e}")
   ```

4. **Common causes and fixes**
   - **No refresh_token** → Re-authenticate with `access_type='offline'`
   - **Invalid client credentials** → Verify client_id and client_secret
   - **User revoked access** → User must re-authenticate
   - **6 months no activity** → User must re-authenticate (very rare)

### 8. Prevention Strategy

**Goal**: 99.9% uptime without requiring re-authentication

1. **Sync regularly** - At least once per week prevents 6-month expiration
2. **Monitor token health** - Alert when issues detected
3. **Proactive refresh** - Refresh tokens before expiration (within 50 minutes of issue)
4. **Graceful degradation** - Disable sync but keep account configuration
5. **User communication** - Clear messaging when re-auth actually needed

### 9. Security Best Practices

1. **Encrypt credentials** - Always use Fernet encryption before database storage
2. **Rotate encryption keys** - Implement key rotation strategy
3. **Minimal scopes** - Only request `gmail.readonly` (we don't need write access)
4. **Secure client secrets** - Never expose client_id/client_secret in frontend
5. **Audit logging** - Log all token operations for security monitoring

## Summary

**The root cause** of "users needing to re-authenticate" is almost always:
1. OAuth flow didn't use `access_type='offline'`
2. Refresh tokens not being saved after refresh
3. User manually revoked access (legitimate case)

**The fix**:
1. ✅ Ensure OAuth flow uses correct parameters
2. ✅ Implement token refresh callback (already done)
3. ✅ Persist token updates in database (already done)
4. ⚠️  Add monitoring and alerts (TODO)
5. ⚠️  Validate existing credentials have refresh tokens (TODO)

With proper implementation, users should **never** need to re-authenticate except when they manually revoke access.
