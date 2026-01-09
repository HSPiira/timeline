#!/usr/bin/env python3
"""
Diagnose email account OAuth credentials and provide fix recommendations.

This script helps identify why tokens are failing and provides actionable fixes.
"""

import asyncio
from datetime import UTC
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def diagnose_account(account_id: str):
    """Diagnose OAuth issues for a specific email account"""
    from datetime import datetime

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from sqlalchemy import select

    from core.database import AsyncSessionLocal
    from integrations.email.encryption import CredentialEncryptor
    from models.email_account import EmailAccount

    async with AsyncSessionLocal() as db:
        # Fetch account
        result = await db.execute(
            select(EmailAccount).where(EmailAccount.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            print(f"❌ Email account not found: {account_id}")
            return

        print(f"\n{'='*60}")
        print(f"📧 Email Account Diagnosis: {account.email_address}")
        print(f"{'='*60}\n")

        # Basic info
        print(f"Provider: {account.provider_type}")
        print(f"Status: {'✅ Active' if account.is_active else '❌ Inactive'}")
        print(f"Created: {account.created_at}")
        print(f"Last Sync: {account.last_sync_at or 'Never'}")
        print()

        # Token health
        print(f"{'─'*60}")
        print("Token Health Status:")
        print(f"{'─'*60}")
        print(f"Last Refreshed: {account.token_last_refreshed_at or '⚠️  Never'}")
        print(f"Refresh Count: {account.token_refresh_count or 0}")
        print(f"Refresh Failures: {account.token_refresh_failures or 0}")

        if account.last_auth_error:
            print(f"Last Error: {account.last_auth_error}")
            print(f"Error Time: {account.last_auth_error_at}")

        print()

        # Decrypt and validate credentials
        print(f"{'─'*60}")
        print("Credential Validation:")
        print(f"{'─'*60}")

        encryptor = CredentialEncryptor()
        try:
            credentials_dict = encryptor.decrypt(account.credentials_encrypted)

            # Check for required fields
            required_fields = [
                "access_token",
                "refresh_token",
                "client_id",
                "client_secret",
            ]
            missing = [f for f in required_fields if not credentials_dict.get(f)]

            if missing:
                print(f"❌ Missing credentials: {', '.join(missing)}")
                print("\n🔧 Fix: Re-authenticate to get complete credentials")
                return

            print("✅ All required fields present:")
            print(f"   - access_token: {credentials_dict['access_token'][:20]}...")
            print(
                f"   - refresh_token: {credentials_dict['refresh_token'][:20]}..."
                if credentials_dict.get("refresh_token")
                else "   - refresh_token: ❌ MISSING"
            )
            print(f"   - client_id: {credentials_dict['client_id']}")
            print("   - client_secret: ***hidden***")
            print()

            # Test token refresh
            print(f"{'─'*60}")
            print("Testing Token Refresh:")
            print(f"{'─'*60}")

            creds = Credentials(
                token=credentials_dict.get("access_token"),
                refresh_token=credentials_dict.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=credentials_dict["client_id"],
                client_secret=credentials_dict["client_secret"],
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            )

            print("Attempting to refresh access token...")
            try:
                creds.refresh(Request())
                print("✅ SUCCESS! Token refresh works!")
                print(f"   New access token: {creds.token[:20]}...")
                print()
                print("🎉 Your tokens are healthy! The system will auto-refresh.")
                print()

                # Offer to save new token
                print(
                    "Would you like to save the refreshed token to the database? (y/n): ",
                    end="",
                )
                response = input().lower()
                if response == "y":
                    updated_creds = {
                        "access_token": creds.token,
                        "refresh_token": creds.refresh_token,
                        "client_id": credentials_dict["client_id"],
                        "client_secret": credentials_dict["client_secret"],
                    }
                    account.credentials_encrypted = encryptor.encrypt(updated_creds)
                    account.token_last_refreshed_at = datetime.now(UTC)
                    account.token_refresh_count = (account.token_refresh_count or 0) + 1
                    account.last_auth_error = None
                    account.last_auth_error_at = None
                    await db.commit()
                    print("✅ Saved refreshed credentials to database!")

            except Exception as e:
                print(f"❌ FAILED: {e}")
                print()
                print("🔧 Root Cause Analysis:")

                error_msg = str(e)
                if "invalid_grant" in error_msg:
                    print("   • Refresh token has been revoked or expired")
                    print("   • This happens when:")
                    print(
                        "     - User manually revoked access in Google account settings"
                    )
                    print("     - 6 months of complete inactivity (rare)")
                    print("     - Initial OAuth didn't use access_type='offline'")
                    print()
                elif "invalid_client" in error_msg:
                    print("   • Client ID or Client Secret is incorrect")
                    print("   • Check your Google Cloud Console credentials")
                    print()
                else:
                    print(f"   • Unexpected error: {error_msg}")
                    print()

                print("💡 Fix Required:")
                print("   1. Re-authenticate through the OAuth API:")
                print(
                    f"      POST /api/oauth-providers/{account.provider_type}/authorize"
                )
                print(f'      {{"subject_id": "{account.subject_id}"}}')
                print()
                print("   2. Follow the returned authorization URL in your browser")
                print()
                print(
                    "   3. After successful OAuth callback, tokens will auto-refresh forever!"
                )
                print()
                print("   Note: OAuth credentials are now managed through the API.")
                print("         See OAUTH_IMPLEMENTATION_STATUS.md for details.")
                print()

        except Exception as e:
            print(f"❌ Failed to decrypt credentials: {e}")
            print("   This may indicate database corruption or encryption key issues")


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Diagnose email account OAuth issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("account_id", help="Email account ID to diagnose")

    args = parser.parse_args()

    asyncio.run(diagnose_account(args.account_id))


if __name__ == "__main__":
    main()
