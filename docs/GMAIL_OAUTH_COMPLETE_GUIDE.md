# Gmail OAuth 2.0 Complete Setup Guide

Complete guide for setting up Gmail OAuth integration with automatic token refresh.

## Overview

The Timeline system now includes a complete OAuth 2.0 flow for Gmail:
- **Automatic token refresh** - Tokens are automatically refreshed when they expire
- **Persistent storage** - Refreshed tokens are saved to the database
- **No manual intervention** - Once authorized, sync works indefinitely

## Architecture

```
User → /auth/gmail/authorize → Google OAuth Consent
Google → /auth/gmail/callback → Save tokens to DB
Sync → Gmail Provider → Auto-refresh tokens → Save to DB
```

## Initial Setup

### Step 1: Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)

2. **Create or Select Project**
   - Click project dropdown → "New Project"
   - Name: "Timeline Email Sync" (or your preference)
   - Click "Create"

3. **Enable Gmail API**
   - Navigate to "APIs & Services" → "Library"
   - Search for "Gmail API"
   - Click "Enable"

4. **Configure OAuth Consent Screen**
   - Go to "APIs & Services" → "OAuth consent screen"
   - Choose "External" (unless you have a Workspace)
   - Fill in required fields:
     - App name: "Timeline"
     - User support email: your email
     - Developer contact: your email
   - Click "Save and Continue"
   - **Scopes**: Add the following:
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.modify`
   - Click "Save and Continue"
   - **Test users**: Add your Gmail address
   - Click "Save and Continue"

5. **Create OAuth Credentials**
   - Go to "APIs & Services" → "Credentials"
   - Click "+ Create Credentials" → "OAuth client ID"
   - Application type: "Web application"
   - Name: "Timeline Web Client"
   - **Authorized redirect URIs**: Add:
     - `http://localhost:8000/auth/gmail/callback`
     - (Add production URL when deploying)
   - Click "Create"
   - **SAVE** the Client ID and Client Secret

### Step 2: Configure Environment Variables

Edit your `.env` file:

```bash
# Gmail OAuth 2.0 Integration
GMAIL_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-your-client-secret
GMAIL_REDIRECT_URI=http://localhost:8000/auth/gmail/callback
GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.modify
```

**Important**:
- Replace with YOUR actual Client ID and Secret from Step 1
- Never commit `.env` to version control
- In production, use environment variables or secrets manager

### Step 3: Restart the Application

```bash
# Stop the server (Ctrl+C)
# Start it again
uvicorn main:app --reload
```

## User Authorization Flow

### Option 1: Via API (Programmatic)

```bash
# 1. Get authorization URL
curl -X GET "http://localhost:8000/auth/gmail/authorize" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Response:
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "message": "Visit auth_url to authorize Gmail access"
}

# 2. Open the auth_url in browser
# - Sign in with Gmail
# - Grant permissions
# - You'll be redirected to callback URL

# 3. The callback endpoint automatically:
# - Exchanges code for tokens
# - Saves to database
# - Returns success message
```

### Option 2: Via Browser (Direct)

1. **Navigate to authorization URL**:
   ```
   http://localhost:8000/auth/gmail/authorize
   ```

2. **Sign in with Google** and grant permissions

3. **Check the response** for confirmation

## Automatic Token Refresh

### How It Works

1. **Gmail API automatically refreshes** access tokens when they expire (every ~1 hour)
2. **Provider detects refresh** by comparing tokens before/after API calls
3. **Callback is triggered** with updated credentials
4. **Sync service saves** encrypted credentials back to database
5. **Next sync uses** the refreshed tokens automatically

### Token Lifecycle

```
Initial Auth → Access Token (1hr) + Refresh Token (permanent)
              ↓
After 1hr →  Gmail API auto-refreshes using Refresh Token
              ↓
Provider →   Detects new Access Token
              ↓
Callback →   Saves to database
              ↓
Next Sync → Uses refreshed tokens
```

### Manual Token Refresh (Optional)

```bash
# Force refresh tokens for an email account
curl -X POST "http://localhost:8000/auth/gmail/refresh/{email_account_id}" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# Response:
{
  "success": true,
  "message": "Tokens refreshed successfully",
  "email_address": "user@gmail.com"
}
```

## Email Sync

### First Sync

```bash
curl -X POST "http://localhost:8000/email-accounts/{account_id}/sync" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Subsequent Syncs

Tokens are automatically refreshed, so you can sync indefinitely:

```bash
# Works even months later - tokens refresh automatically
curl -X POST "http://localhost:8000/email-accounts/{account_id}/sync" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Troubleshooting

### Error: "unauthorized_client: Unauthorized"

**Cause**: OAuth client credentials mismatch or revoked access

**Solution**:
1. Verify `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` in `.env` match Google Cloud Console
2. Check redirect URI matches exactly
3. Re-authorize via `/auth/gmail/authorize`

### Error: "No refresh token available"

**Cause**: OAuth flow didn't include `prompt=consent`

**Solution**:
1. The `/auth/gmail/authorize` endpoint now includes `prompt=consent` automatically
2. Re-authorize the account
3. If problem persists, revoke access in [Google Account](https://myaccount.google.com/permissions) and re-authorize

### Error: "Refresh token expired"

**Cause**: Refresh tokens can expire if:
- Not used for 6 months (inactive users)
- User revoked access manually
- User changed password
- OAuth app security changed

**Solution**:
1. Re-authorize via `/auth/gmail/authorize`
2. Consider setting up scheduled syncs to keep tokens active

### Tokens Not Being Saved

**Symptoms**: Sync works initially but fails after 1 hour

**Debugging**:
```python
# Check logs for:
logger.info(f"Tokens refreshed for {email_address}")
logger.info(f"Saved refreshed tokens for {email_address}")

# If you see the first but not the second, check database permissions
```

## Production Deployment

### Security Checklist

- [ ] Use environment variables for all OAuth credentials
- [ ] Never commit `.env` or credentials to Git
- [ ] Use HTTPS for redirect URIs in production
- [ ] Set up proper CORS origins
- [ ] Use secrets manager (AWS Secrets Manager, Google Secret Manager, etc.)
- [ ] Monitor for unauthorized access attempts
- [ ] Set up logging and alerting for OAuth failures
- [ ] Regularly audit OAuth permissions

### Production Configuration

```bash
# Production .env
GMAIL_CLIENT_ID=prod-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-prod-secret
GMAIL_REDIRECT_URI=https://yourdomain.com/auth/gmail/callback
GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.modify
```

**Google Cloud Console**:
- Update redirect URIs to production URL
- Move app from "Testing" to "In Production"
- Set up OAuth verification if publishing publicly

## API Endpoints Reference

### Authorization

```
GET /auth/gmail/authorize
Authorization: Bearer {token}

Response:
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "message": "Visit auth_url to authorize Gmail access"
}
```

### OAuth Callback (Auto-called by Google)

```
GET /auth/gmail/callback?code={code}&state={user_id}

Response:
{
  "success": true,
  "message": "Gmail account user@gmail.com authorized successfully",
  "email_account_id": "account_id",
  "email_address": "user@gmail.com",
  "has_refresh_token": true
}
```

### Manual Token Refresh

```
POST /auth/gmail/refresh/{email_account_id}
Authorization: Bearer {token}

Response:
{
  "success": true,
  "message": "Tokens refreshed successfully",
  "email_address": "user@gmail.com"
}
```

### Email Sync

```
POST /email-accounts/{account_id}/sync
Authorization: Bearer {token}

Response:
{
  "messages_fetched": 42,
  "events_created": 42,
  "provider": "gmail",
  "sync_type": "incremental"
}
```

## Architecture Details

### Token Storage

Tokens are encrypted using Fernet encryption before storage:

```python
# Credentials stored in database:
{
  "access_token": "ya29.a0Af...",
  "refresh_token": "1//0gZ...",
  "client_id": "123...apps.googleusercontent.com",
  "client_secret": "GOCSPX-..."
}
```

### Automatic Refresh Flow

```python
# 1. Provider connects with credentials
provider.connect(config)

# 2. Set up callback
provider.set_token_refresh_callback(save_to_db)

# 3. Fetch messages (may trigger refresh)
messages = await provider.fetch_messages()

# 4. If tokens refreshed, callback is called
# 5. Callback saves encrypted tokens to database
# 6. Next sync uses refreshed tokens
```

## Best Practices

1. **Schedule Regular Syncs**
   - Keep tokens active (prevents 6-month expiry)
   - Use background jobs (Celery, cron, etc.)
   - Recommended: Sync every 15-30 minutes

2. **Monitor OAuth Status**
   - Log all OAuth events
   - Alert on refresh failures
   - Track token age

3. **Handle Errors Gracefully**
   - Catch OAuth errors
   - Retry with exponential backoff
   - Notify users when re-auth needed

4. **Security**
   - Rotate client secrets periodically
   - Audit OAuth permissions regularly
   - Monitor for suspicious activity
   - Use least-privilege scopes

## Support

For issues or questions:
1. Check logs: Look for OAuth-related errors
2. Verify setup: Ensure all environment variables are set
3. Test OAuth flow: Try manual authorization
4. Check Google Cloud Console: Verify API is enabled and credentials are correct
