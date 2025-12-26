# Gmail OAuth 2.0 Setup Guide

This guide walks you through setting up Gmail OAuth 2.0 credentials for the Timeline email integration system.

## Prerequisites

- Google Cloud Platform account
- Gmail account for testing
- Timeline application running

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "NEW PROJECT"
3. Enter project name: `Timeline Email Integration`
4. Click "CREATE"

## Step 2: Enable Gmail API

1. In your project, go to **APIs & Services** → **Library**
2. Search for "Gmail API"
3. Click **Gmail API**
4. Click **ENABLE**

## Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **User type**:
   - **Internal**: If using Google Workspace (for organization users only)
   - **External**: For testing with personal Gmail accounts
3. Click **CREATE**

### Fill in App Information:

```
App name: Timeline Email Integration
User support email: <your-email>
Developer contact information: <your-email>
```

4. Click **SAVE AND CONTINUE**

### Add Scopes:

5. Click **ADD OR REMOVE SCOPES**
6. Filter and select these scopes:

```
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.modify
```

7. Click **UPDATE** → **SAVE AND CONTINUE**

### Add Test Users (if External):

8. Click **ADD USERS**
9. Enter Gmail addresses that can test the integration
10. Click **ADD** → **SAVE AND CONTINUE**

## Step 4: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **CREATE CREDENTIALS** → **OAuth client ID**
3. Application type: **Web application**
4. Name: `Timeline Web Client`

### Configure Redirect URIs:

Add these authorized redirect URIs:

```
http://localhost:8000/auth/gmail/callback
https://yourdomain.com/auth/gmail/callback
```

5. Click **CREATE**

### Save Your Credentials:

You'll see a modal with:
- **Client ID**: `xxxxx.apps.googleusercontent.com`
- **Client Secret**: `GOCSPX-xxxxx`

**IMPORTANT**: Copy these immediately - you'll need them for `.env`

## Step 5: Configure Timeline Application

### Update `.env` file:

Add the following to your `.env` file:

```bash
# ============================================================================
# Gmail OAuth 2.0 Integration
# ============================================================================
GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-your-client-secret
GMAIL_REDIRECT_URI=http://localhost:8000/auth/gmail/callback
GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.modify
```

### Restart the application:

```bash
# Stop the server if running
# Restart to pick up new environment variables
uvicorn main:app --reload
```

## Step 6: Obtain User Access Token

### Option A: Using OAuth Flow (Recommended)

1. Navigate to the OAuth authorization endpoint:

```bash
GET http://localhost:8000/auth/gmail/authorize
```

2. You'll be redirected to Google's consent screen
3. Sign in with the test Gmail account
4. Grant permissions
5. You'll be redirected back with an authorization code
6. Exchange the code for tokens (handled automatically)

### Option B: Manual Token Generation (For Testing)

Use Google's OAuth 2.0 Playground:

1. Go to [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)
2. Click the gear icon (⚙️) in the top-right
3. Check "Use your own OAuth credentials"
4. Enter your Client ID and Client Secret
5. In **Step 1**: Select Gmail API v1 scopes:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
6. Click **Authorize APIs**
7. Sign in and grant permissions
8. In **Step 2**: Click **Exchange authorization code for tokens**
9. Copy the tokens

## Step 7: Create Email Account in Timeline

### Using the API:

```bash
POST http://localhost:8000/api/email-accounts
Content-Type: application/json
X-Tenant-ID: <your-tenant-id>
Authorization: Bearer <your-jwt-token>

{
  "provider_type": "gmail",
  "email_address": "your-email@gmail.com",
  "credentials": {
    "access_token": "ya29.a0...",
    "refresh_token": "1//0g...",
    "client_id": "xxxxx.apps.googleusercontent.com",
    "client_secret": "GOCSPX-xxxxx"
  }
}
```

### Response:

```json
{
  "id": "clq123...",
  "tenant_id": "clq456...",
  "subject_id": "clq789...",
  "provider_type": "gmail",
  "email_address": "your-email@gmail.com",
  "is_active": true,
  "created_at": "2025-12-26T10:00:00Z"
}
```

## Step 8: Test Email Sync

### Trigger manual sync:

```bash
POST http://localhost:8000/api/email-accounts/{account_id}/sync
Content-Type: application/json
X-Tenant-ID: <your-tenant-id>
Authorization: Bearer <your-jwt-token>

{
  "incremental": true
}
```

### Response:

```json
{
  "messages_fetched": 25,
  "events_created": 25,
  "provider": "gmail",
  "sync_type": "incremental"
}
```

## Troubleshooting

### Error: "Access blocked: Timeline Email Integration has not completed the Google verification process"

**Solution**: Your app is in "Testing" mode.
1. Go to **OAuth consent screen**
2. Add the Gmail address as a test user
3. Or publish the app (requires verification for production)

### Error: "invalid_grant"

**Solution**: Refresh token expired or revoked.
1. Generate new tokens using OAuth 2.0 Playground
2. Update credentials in Timeline

### Error: "insufficient_scope"

**Solution**: Missing required scopes.
1. Check that both scopes are configured:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
2. Re-authorize the application

### Error: "redirect_uri_mismatch"

**Solution**: Redirect URI doesn't match configured URIs.
1. Go to **Credentials** → Your OAuth Client
2. Add the exact redirect URI you're using
3. Wait a few minutes for changes to propagate

## Security Best Practices

### Production Deployment:

1. **Use Environment Variables**: Never hardcode credentials
2. **Encrypt Credentials**: Timeline automatically encrypts credentials at rest
3. **Rotate Secrets**: Periodically rotate Client Secret
4. **Limit Scopes**: Only request minimum required scopes
5. **Monitor Access**: Use Google Cloud Console to monitor API usage
6. **Use HTTPS**: Always use HTTPS in production redirect URIs

### Token Management:

- **Access Token**: Short-lived (1 hour), automatically refreshed
- **Refresh Token**: Long-lived, securely stored encrypted
- **Revocation**: Users can revoke access at [Google Account Settings](https://myaccount.google.com/permissions)

## Architecture Overview

```
┌─────────────────┐
│   User Gmail    │
│    Account      │
└────────┬────────┘
         │ OAuth 2.0
         ▼
┌─────────────────┐
│  Google OAuth   │
│    Server       │
└────────┬────────┘
         │ Authorization Code
         ▼
┌─────────────────┐      ┌──────────────────┐
│   Timeline API  │◄────►│  Gmail API       │
│  (OAuth Client) │      │  (Resource)      │
└────────┬────────┘      └──────────────────┘
         │
         ▼
┌─────────────────┐
│   Timeline DB   │
│ (Encrypted      │
│  Credentials)   │
└─────────────────┘
```

## Additional Resources

- [Gmail API Documentation](https://developers.google.com/gmail/api)
- [OAuth 2.0 Overview](https://developers.google.com/identity/protocols/oauth2)
- [Google Cloud Console](https://console.cloud.google.com/)
- [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)

## Support

For issues specific to Timeline:
- Check logs in `logs/timeline.log`
- Review error messages in API responses
- Consult Timeline documentation

For Google OAuth issues:
- [Google OAuth Support](https://support.google.com/cloud/answer/6158849)
- [Stack Overflow: google-oauth](https://stackoverflow.com/questions/tagged/google-oauth)
