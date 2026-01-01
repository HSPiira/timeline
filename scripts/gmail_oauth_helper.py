#!/usr/bin/env python3
"""
Gmail OAuth Helper - Ensure tokens never expire

This script helps with:
1. Validating existing OAuth tokens
2. Generating new OAuth tokens with proper settings to prevent expiration
3. Testing token refresh functionality

IMPORTANT: For tokens to auto-refresh indefinitely, the OAuth flow MUST use:
- access_type='offline' (to get refresh token)
- prompt='consent' (to get new refresh token each time)
- Correct scopes: https://www.googleapis.com/auth/gmail.readonly

Refresh tokens only expire when:
- User revokes access manually
- 6 months of non-use (very rare with active sync)
- Security issues detected by Google
"""

import asyncio
import sys
from datetime import datetime, timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow


# Gmail API scope (read-only for safety)
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def validate_credentials(credentials_dict: dict) -> dict:
    """Validate OAuth credentials and check if they can auto-refresh"""
    print("\n=== Validating OAuth Credentials ===\n")

    required_keys = ['access_token', 'refresh_token', 'client_id', 'client_secret']
    missing = [k for k in required_keys if not credentials_dict.get(k)]

    if missing:
        return {
            'valid': False,
            'error': f"Missing required keys: {missing}",
            'recommendation': "Generate new tokens using this script"
        }

    # Build credentials object
    creds = Credentials(
        token=credentials_dict.get('access_token'),
        refresh_token=credentials_dict.get('refresh_token'),
        token_uri='https://oauth2.googleapis.com/token',
        client_id=credentials_dict['client_id'],
        client_secret=credentials_dict['client_secret'],
        scopes=SCOPES
    )

    result = {
        'valid': True,
        'has_refresh_token': bool(creds.refresh_token),
        'token_expired': creds.expired if hasattr(creds, 'expired') else 'unknown',
        'scopes': creds.scopes if hasattr(creds, 'scopes') else []
    }

    # Try to refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            print("Access token expired, attempting refresh...")
            creds.refresh(Request())
            result['refresh_successful'] = True
            result['new_access_token'] = creds.token
            result['recommendation'] = "Token refresh works! Update your credentials with the new access token."
        except Exception as e:
            result['refresh_successful'] = False
            result['refresh_error'] = str(e)
            result['recommendation'] = (
                "Token refresh FAILED. Generate new tokens using this script. "
                "Common causes: refresh token expired (6 months unused), user revoked access, "
                "or incorrect client_id/client_secret."
            )
    elif not creds.refresh_token:
        result['recommendation'] = (
            "No refresh token! OAuth flow must use access_type='offline'. "
            "Generate new tokens using this script."
        )
    else:
        result['recommendation'] = "Credentials look good. Token will auto-refresh when needed."

    return result


def generate_new_credentials(client_id: str, client_secret: str) -> dict:
    """
    Generate new OAuth credentials with proper settings for auto-refresh.

    This launches a local web server and opens a browser for OAuth consent.
    """
    print("\n=== Generating New OAuth Credentials ===\n")
    print("IMPORTANT: This will open a browser for Google OAuth consent.")
    print("Make sure you approve all requested permissions.\n")

    # Create OAuth flow with correct settings
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8080/"]
            }
        },
        scopes=SCOPES,
        # CRITICAL: These parameters ensure we get a non-expiring refresh token
        redirect_uri='http://localhost:8080/'
    )

    # Run the OAuth flow
    # access_type='offline' ensures we get a refresh token
    # prompt='consent' forces consent screen to ensure we get a NEW refresh token
    creds = flow.run_local_server(
        port=8080,
        access_type='offline',
        prompt='consent',
        open_browser=True
    )

    print("\n✅ OAuth consent successful!\n")

    credentials_dict = {
        'access_token': creds.token,
        'refresh_token': creds.refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
        'token_uri': creds.token_uri,
        'scopes': creds.scopes,
        'expiry': creds.expiry.isoformat() if creds.expiry else None
    }

    return credentials_dict


async def test_gmail_access(credentials_dict: dict, email_address: str = 'me'):
    """Test Gmail API access with the credentials"""
    print("\n=== Testing Gmail API Access ===\n")

    from googleapiclient.discovery import build

    creds = Credentials(
        token=credentials_dict.get('access_token'),
        refresh_token=credentials_dict.get('refresh_token'),
        token_uri='https://oauth2.googleapis.com/token',
        client_id=credentials_dict['client_id'],
        client_secret=credentials_dict['client_secret'],
        scopes=SCOPES
    )

    try:
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()

        print(f"✅ Successfully connected to Gmail!")
        print(f"   Email: {profile.get('emailAddress')}")
        print(f"   Total Messages: {profile.get('messagesTotal')}")
        print(f"   Total Threads: {profile.get('threadsTotal')}")

        # Test fetching a message
        results = service.users().messages().list(userId='me', maxResults=1).execute()
        if results.get('messages'):
            print(f"   ✅ Can fetch messages")
        else:
            print(f"   ⚠️  Mailbox appears empty")

        return True

    except Exception as e:
        print(f"❌ Failed to access Gmail: {e}")
        return False


def main():
    """Main CLI interface"""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Gmail OAuth Helper - Prevent token expiration issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate existing credentials
  %(prog)s validate --credentials credentials.json

  # Generate new credentials
  %(prog)s generate --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

  # Generate and save to file
  %(prog)s generate --client-id YOUR_ID --client-secret YOUR_SECRET --output creds.json

  # Test credentials
  %(prog)s test --credentials credentials.json
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate existing credentials')
    validate_parser.add_argument('--credentials', required=True, help='Path to credentials JSON file')

    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate new credentials')
    generate_parser.add_argument('--client-id', required=True, help='Google OAuth Client ID')
    generate_parser.add_argument('--client-secret', required=True, help='Google OAuth Client Secret')
    generate_parser.add_argument('--output', help='Output file for credentials (optional)')

    # Test command
    test_parser = subparsers.add_parser('test', help='Test Gmail API access')
    test_parser.add_argument('--credentials', required=True, help='Path to credentials JSON file')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Validate command
    if args.command == 'validate':
        with open(args.credentials, 'r') as f:
            credentials_dict = json.load(f)

        result = validate_credentials(credentials_dict)
        print("\nValidation Result:")
        print(json.dumps(result, indent=2))

        if result.get('refresh_successful') and result.get('new_access_token'):
            print("\n💾 Save this new access token to your credentials:")
            print(f"   access_token: {result['new_access_token']}")

    # Generate command
    elif args.command == 'generate':
        credentials_dict = generate_new_credentials(args.client_id, args.client_secret)

        print("\n✅ New credentials generated successfully!\n")
        print("Credentials:")
        print(json.dumps(credentials_dict, indent=2))

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(credentials_dict, f, indent=2)
            print(f"\n💾 Saved to {args.output}")

        print("\n⚠️  IMPORTANT: Store these credentials securely!")
        print("   - Never commit to git")
        print("   - Encrypt before storing in database")
        print("   - The refresh_token is especially sensitive\n")

    # Test command
    elif args.command == 'test':
        with open(args.credentials, 'r') as f:
            credentials_dict = json.load(f)

        asyncio.run(test_gmail_access(credentials_dict))


if __name__ == '__main__':
    main()
