# Email OAuth Setup Guide

Complete guide for setting up OAuth authentication for email providers in Timeline.

## Overview

Timeline uses OAuth 2.0 to securely access email accounts without storing passwords. This guide walks you through setting up OAuth for different email providers.

**Supported Providers:**
- Gmail (Google)
- Outlook/Office 365 (Microsoft)
- Yahoo Mail
- Any IMAP server (uses password authentication, not OAuth)

---

## Quick Start: OAuth Setup Wizard

The fastest way to set up OAuth is using our interactive wizard:

```bash
# Gmail
python scripts/oauth_setup_wizard.py --provider gmail --email your@gmail.com

# Outlook
python scripts/oauth_setup_wizard.py --provider outlook --email your@outlook.com

# Yahoo
python scripts/oauth_setup_wizard.py --provider yahoo --email your@yahoo.com
```

The wizard will:
1. Prompt for OAuth client credentials
2. Open your browser for authorization
3. Exchange authorization code for tokens
4. Validate token configuration
5. Test the connection
6. Save credentials to a JSON file

**Output:** Ready-to-use credentials file at `/tmp/{provider}_credentials.json`

---

## Provider Setup Instructions

### Gmail (Google)

#### Step 1: Create OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Navigate to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "OAuth client ID"
5. If prompted, configure OAuth consent screen:
   - User Type: External (for personal use) or Internal (for organization)
   - App name: "Timeline Email Integration"
   - Scopes: Add `gmail.readonly` and `gmail.modify`
   - Test users: Add your email address
6. Application type: "Web application"
7. Authorized redirect URIs: `http://localhost:8080/callback`
8. Copy the Client ID and Client Secret

#### Step 2: Enable Gmail API

1. In Google Cloud Console, go to "APIs & Services" > "Library"
2. Search for "Gmail API"
3. Click "Enable"

#### Step 3: Run OAuth Wizard

```bash
python scripts/oauth_setup_wizard.py --provider gmail --email your@gmail.com
```

Enter your Client ID and Client Secret when prompted.

#### Step 4: Authorize

1. Wizard opens your browser
2. Select your Google account
3. Review permissions (read and modify email)
4. Click "Allow"
5. Browser redirects to localhost and closes

#### Step 5: Save Credentials

The wizard saves credentials to `/tmp/gmail_credentials.json`:

```json
{
  "access_token": "ya29.a0AfH6SMB...",
  "refresh_token": "1//0gZ5K9X...",
  "client_id": "123456789.apps.googleusercontent.com",
  "client_secret": "ABC123...",
  "expires_at": "2025-12-27T01:30:00Z",
  "scope": "https://www.googleapis.com/auth/gmail.readonly ..."
}
```

#### Important Gmail Notes

- **Refresh Token**: Gmail refresh tokens don't expire unless:
  - User revokes access manually
  - 6 months of complete inactivity (no API calls)
  - User changes password
- **Auto-Refresh**: Access tokens refresh automatically every hour
- **Scopes**: Timeline uses `gmail.readonly` and `gmail.modify` (for marking as read)
- **Test Users**: During development, add test users to OAuth consent screen

---

### Outlook/Office 365 (Microsoft)

#### Step 1: Register Application

1. Go to [Azure Portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Click "New registration"
3. Name: "Timeline Email Integration"
4. Supported account types: "Accounts in any organizational directory and personal Microsoft accounts"
5. Redirect URI:
   - Platform: "Web"
   - URI: `http://localhost:8080/callback`
6. Click "Register"

#### Step 2: Configure API Permissions

1. In your app registration, go to "API permissions"
2. Click "Add a permission"
3. Select "Microsoft Graph"
4. Choose "Delegated permissions"
5. Add these permissions:
   - `Mail.Read` - Read email
   - `Mail.ReadWrite` - Modify email (mark as read)
   - `offline_access` - **CRITICAL**: Required for refresh tokens
6. Click "Add permissions"

#### Step 3: Create Client Secret

1. Go to "Certificates & secrets"
2. Click "New client secret"
3. Description: "Timeline Integration"
4. Expires: "24 months" (recommended)
5. Click "Add"
6. **Copy the secret value immediately** (won't be shown again)

#### Step 4: Get Client Information

- Client ID: Found in "Overview" page (Application ID)
- Tenant ID: Found in "Overview" page (Directory ID)
- Client Secret: Created in previous step

#### Step 5: Run OAuth Wizard

```bash
python scripts/oauth_setup_wizard.py --provider outlook --email your@outlook.com
```

#### Important Outlook Notes

- **Refresh Token**: Only returned if `offline_access` scope is included
- **Expiration**: Client secrets expire (choose 24 months)
- **Multi-tenant**: Works with both personal and organizational accounts
- **Graph API**: Uses Microsoft Graph API (not legacy Outlook API)

---

### Yahoo Mail

#### Step 1: Create Yahoo App

1. Go to [Yahoo Developer Apps](https://developer.yahoo.com/apps/)
2. Click "Create an App"
3. Application Name: "Timeline Email Integration"
4. Application Type: "Web Application"
5. Redirect URI: `http://localhost:8080/callback`
6. API Permissions: Select "Mail" with "Read" and "Write"

#### Step 2: Run OAuth Wizard

```bash
python scripts/oauth_setup_wizard.py --provider yahoo --email your@yahoo.com
```

#### Important Yahoo Notes

- **Refresh Token**: Yahoo refresh tokens are long-lived
- **Rate Limits**: More restrictive than Gmail/Outlook
- **IMAP Alternative**: Yahoo also supports IMAP (simpler setup)

---

## Using OAuth Credentials

### Create Email Account (New)

After running the wizard, use the credentials file to create an email account:

```bash
# Read credentials from wizard output
cat /tmp/gmail_credentials.json

# Create email account via API
curl -X POST http://localhost:8000/email-accounts/ \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_type": "gmail",
    "email_address": "your@gmail.com",
    "credentials": {
      "access_token": "ya29.a0AfH6SMB...",
      "refresh_token": "1//0gZ5K9X...",
      "client_id": "123456789.apps.googleusercontent.com",
      "client_secret": "ABC123..."
    },
    "connection_params": {}
  }'
```

### Update Email Account (Existing)

To fix expired tokens for an existing account:

```bash
# Get account ID from list endpoint
curl http://localhost:8000/email-accounts/ \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN"

# Update credentials
curl -X PATCH http://localhost:8000/email-accounts/{account_id} \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "credentials": {
      "access_token": "new_access_token...",
      "refresh_token": "new_refresh_token...",
      "client_id": "client_id",
      "client_secret": "client_secret"
    }
  }'
```

### Test Sync

After creating/updating the account, test email sync:

```bash
curl -X POST http://localhost:8000/email-accounts/{account_id}/sync \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"incremental": false}'
```

---

## Token Management

### How Auto-Refresh Works

1. **Access Token Expires** (after 1 hour)
2. **System Detects Expiration** (on next API call)
3. **Auto-Refresh** (using refresh token)
4. **New Access Token** (valid for 1 hour)
5. **Saved to Database** (automatically)
6. **Sync Continues** (no user action needed)

### Monitoring Token Health

Check token status in database:

```sql
SELECT
    email_address,
    token_refresh_count,
    token_last_refreshed_at,
    token_refresh_failures,
    last_auth_error,
    last_sync_at
FROM email_account
WHERE provider_type = 'gmail';
```

**Healthy Account:**
- `token_refresh_count` > 0 (increases regularly)
- `token_last_refreshed_at` recent (within last day)
- `token_refresh_failures` = 0
- `last_auth_error` = NULL

**Unhealthy Account:**
- `token_refresh_failures` > 3
- `last_auth_error` contains "invalid_grant" or "invalid_client"
- `token_last_refreshed_at` is NULL or very old

### Preventing Token Expiration

**Critical OAuth Parameters:**

1. **Gmail**:
   - `access_type='offline'` - **MUST** be included
   - `prompt='consent'` - Forces new refresh token
   - Without these: Refresh token won't be returned

2. **Outlook**:
   - `offline_access` scope - **MUST** be included
   - Without this: Only access token, no refresh token

3. **Yahoo**:
   - Standard OAuth flow includes refresh token by default

**Our wizard ensures these parameters are always set correctly.**

---

## Troubleshooting

### Error: "Token has been expired or revoked"

**Causes:**
1. Refresh token not obtained initially (`access_type='offline'` missing)
2. User manually revoked access in account settings
3. 6 months of no activity (rare)
4. Invalid client credentials

**Solution:**
```bash
# Re-run OAuth wizard to get fresh tokens
python scripts/oauth_setup_wizard.py --provider gmail --email your@gmail.com

# Update account with new credentials
curl -X PATCH http://localhost:8000/email-accounts/{account_id} -d '{...}'
```

### Error: "Missing refresh_token"

**Cause:** OAuth flow didn't include required parameters

**Solution:**
- Use the OAuth wizard (ensures correct parameters)
- Manual flow: Add `access_type='offline'` (Gmail) or `offline_access` scope (Outlook)

### Error: "invalid_client"

**Causes:**
1. Wrong client_id or client_secret
2. Client secret expired (Outlook only)
3. OAuth app deleted or disabled

**Solution:**
1. Verify credentials in provider console
2. Generate new client secret (Outlook)
3. Re-run OAuth wizard with correct credentials

### Error: "redirect_uri_mismatch"

**Cause:** Redirect URI doesn't match console configuration

**Solution:**
1. Check redirect URI in provider console
2. Default is `http://localhost:8080/callback`
3. Must match exactly (including http vs https, port, path)

### Connection Test Fails

**Causes:**
1. API not enabled (Gmail API)
2. Wrong scopes requested
3. Permissions not granted in OAuth consent

**Solution:**
1. Enable Gmail API in Google Cloud Console
2. Verify scopes match what's configured
3. Re-run OAuth flow and ensure all permissions granted

---

## Security Best Practices

### Credential Storage

- ✅ **DO**: Encrypt credentials before storing in database
- ✅ **DO**: Use environment variables for encryption keys
- ✅ **DO**: Rotate encryption keys periodically
- ❌ **DON'T**: Store credentials in plain text
- ❌ **DON'T**: Commit credentials to git
- ❌ **DON'T**: Expose credentials in logs

### Client Secrets

- ✅ **DO**: Keep client_id and client_secret in environment variables
- ✅ **DO**: Use different OAuth apps for dev/staging/production
- ✅ **DO**: Rotate client secrets annually (Outlook)
- ❌ **DON'T**: Hardcode in source code
- ❌ **DON'T**: Share across environments
- ❌ **DON'T**: Expose in frontend code

### Refresh Tokens

- ✅ **DO**: Treat refresh tokens as sensitive as passwords
- ✅ **DO**: Encrypt in database
- ✅ **DO**: Monitor for unusual refresh activity
- ❌ **DON'T**: Log refresh tokens
- ❌ **DON'T**: Send in URL parameters
- ❌ **DON'T**: Store in frontend localStorage

---

## Advanced Topics

### Custom Redirect URIs

For production deployment with custom redirect URIs:

```bash
python scripts/oauth_setup_wizard.py --provider gmail
# When prompted for redirect URI, enter:
# https://yourdomain.com/auth/gmail/callback
```

Then configure your application to handle the callback at that endpoint.

### Batch Account Setup

To set up multiple accounts:

```bash
for email in user1@gmail.com user2@gmail.com user3@gmail.com; do
  python scripts/oauth_setup_wizard.py --provider gmail --email $email
  # Save output to separate files
done
```

### Re-authentication Flow

When tokens expire, guide users through re-authentication:

1. Detect authentication error (401 Unauthorized)
2. Notify user: "Email account needs re-authentication"
3. Provide link to OAuth wizard or custom re-auth flow
4. After success, update credentials via PATCH endpoint

---

## FAQ

**Q: Do refresh tokens expire?**
A: Generally no, unless:
- User revokes access manually
- 6 months of complete inactivity (Gmail)
- User changes password
- Provider security policy changes

**Q: How often do I need to re-authenticate?**
A: Never, if OAuth is configured correctly with `access_type='offline'` (Gmail) or `offline_access` scope (Outlook). The system auto-refreshes indefinitely.

**Q: Can I use the same OAuth app for multiple accounts?**
A: Yes! One OAuth app (client_id/client_secret) can be used for unlimited email accounts.

**Q: What happens if my client secret expires? (Outlook)**
A: Generate a new client secret in Azure Portal, then update all accounts using that OAuth app with the new secret.

**Q: Is it safe to use localhost redirect URI?**
A: Yes for development. For production, use HTTPS redirect URIs on your domain.

**Q: Can I automate OAuth without browser?**
A: No, OAuth requires user interaction for security. Service accounts are an alternative for server-to-server scenarios (Gmail only).

---

## Next Steps

1. ✅ Run OAuth wizard for your email provider
2. ✅ Create email account via API with obtained credentials
3. ✅ Test email sync
4. ✅ Monitor token health in database
5. ✅ Set up monitoring/alerts for authentication failures

For issues or questions, check the troubleshooting section or open an issue on GitHub.
