#!/usr/bin/env python3
"""
OAuth Setup Wizard for Email Providers

Interactive CLI tool that guides users through OAuth setup for email providers.
Ensures tokens are configured correctly to prevent expiration issues.

Usage:
    python scripts/oauth_setup_wizard.py --provider gmail
    python scripts/oauth_setup_wizard.py --provider outlook
    python scripts/oauth_setup_wizard.py --provider gmail --email user@example.com
"""

import asyncio
import sys
import os
import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from threading import Thread
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.email.oauth_manager import UnifiedOAuthManager, OAUTH_PROVIDERS


# Global variable to store callback data
callback_data = {}


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP server handler for OAuth callback"""

    def do_GET(self):
        """Handle OAuth callback request"""
        global callback_data

        # Parse query parameters
        query_components = parse_qs(urlparse(self.path).query)

        if 'code' in query_components:
            code = query_components['code'][0]
            state = query_components.get('state', [None])[0]

            callback_data['code'] = code
            callback_data['state'] = state
            callback_data['error'] = None

            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            success_html = """
            <html>
            <head><title>Authorization Successful</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #4CAF50;">✅ Authorization Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
                <script>window.close();</script>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode())

        elif 'error' in query_components:
            error = query_components['error'][0]
            error_description = query_components.get('error_description', ['Unknown error'])[0]

            callback_data['code'] = None
            callback_data['state'] = None
            callback_data['error'] = f"{error}: {error_description}"

            # Send error response
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            error_html = f"""
            <html>
            <head><title>Authorization Failed</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #f44336;">❌ Authorization Failed</h1>
                <p>{error}: {error_description}</p>
                <p>Please return to the terminal and try again.</p>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())

    def log_message(self, format, *args):
        """Suppress server logs"""
        pass


async def run_oauth_flow(provider_type: str, email: str = None):
    """
    Run interactive OAuth flow for email provider.

    Args:
        provider_type: Provider type ('gmail', 'outlook', 'yahoo')
        email: Optional email address hint
    """
    global callback_data

    provider_config = OAUTH_PROVIDERS[provider_type]

    print(f"\n{'='*60}")
    print(f"OAuth Setup Wizard for {provider_config.name}")
    print(f"{'='*60}\n")

    # Step 1: Get client credentials
    print("Step 1: Enter OAuth Client Credentials")
    print(f"(Get these from {get_console_url(provider_type)})\n")

    client_id = input("Client ID: ").strip()
    if not client_id:
        print("❌ Client ID is required")
        sys.exit(1)

    client_secret = input("Client Secret: ").strip()
    if not client_secret:
        print("❌ Client Secret is required")
        sys.exit(1)

    # Step 2: Configure redirect URI
    print("\n" + "─"*60)
    print("Step 2: Configure Redirect URI")
    print("─"*60)

    default_redirect = "http://localhost:8080/callback"
    custom_redirect = input(f"\nRedirect URI (press Enter for {default_redirect}): ").strip()
    redirect_uri = custom_redirect if custom_redirect else default_redirect

    print(f"\n✅ Using redirect URI: {redirect_uri}")
    print(f"⚠️  Make sure this is configured in {get_console_url(provider_type)}\n")

    # Step 3: Start local server for callback
    print("─"*60)
    print("Step 3: Starting Local OAuth Server")
    print("─"*60)

    # Extract port from redirect URI
    port = int(urlparse(redirect_uri).netloc.split(':')[1]) if ':' in urlparse(redirect_uri).netloc else 8080

    server = HTTPServer(('localhost', port), OAuthCallbackHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print(f"\n✅ OAuth callback server started on port {port}")

    # Step 4: Generate authorization URL
    print("\n" + "─"*60)
    print("Step 4: Authorize Application")
    print("─"*60)

    manager = UnifiedOAuthManager(
        provider_type=provider_type,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri
    )

    auth_url, state = manager.get_authorization_url()

    if email:
        # Add login hint if email provided
        auth_url += f"&login_hint={email}"

    print("\nOpening browser for authorization...")
    print(f"If browser doesn't open, visit this URL:\n")
    print(f"  {auth_url}\n")

    # Open browser
    try:
        webbrowser.open(auth_url)
        print("✅ Browser opened")
    except:
        print("⚠️  Could not open browser automatically")

    print("\nWaiting for authorization...")
    print("(This will timeout after 5 minutes)\n")

    # Wait for callback (with timeout)
    timeout = 300  # 5 minutes
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(1)
        elapsed += 1

        if callback_data.get('code') or callback_data.get('error'):
            break

        if elapsed % 10 == 0:
            print(f"Waiting... ({elapsed}s / {timeout}s)")

    server.shutdown()

    if callback_data.get('error'):
        print(f"\n❌ Authorization failed: {callback_data['error']}")
        sys.exit(1)

    if not callback_data.get('code'):
        print("\n❌ Authorization timeout - no callback received")
        print("Please check:")
        print("  1. Redirect URI matches the one in provider console")
        print("  2. Firewall allows connections to localhost")
        print("  3. You completed the authorization in the browser")
        sys.exit(1)

    # Step 5: Exchange code for tokens
    print("─"*60)
    print("Step 5: Exchanging Code for Tokens")
    print("─"*60 + "\n")

    try:
        tokens = await manager.exchange_code_for_tokens(
            code=callback_data['code'],
            state=callback_data['state']
        )

        print("✅ Successfully obtained tokens!")

        # Validate tokens
        is_valid, errors = manager.validate_tokens(tokens)

        if not is_valid:
            print("\n⚠️  Token Validation Warnings:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("\n✅ Tokens validated successfully!")

        # Step 6: Test connection
        print("\n" + "─"*60)
        print("Step 6: Testing Connection")
        print("─"*60 + "\n")

        await test_email_connection(provider_type, tokens)

        # Step 7: Display results
        print("\n" + "="*60)
        print("🎉 OAuth Setup Complete!")
        print("="*60 + "\n")

        print("Credentials (save these securely):")
        print("─"*60)

        # Create credentials dict without exposing full tokens in terminal
        safe_display = {
            'access_token': tokens['access_token'][:30] + '...',
            'refresh_token': tokens['refresh_token'][:30] + '...' if tokens.get('refresh_token') else None,
            'client_id': client_id,
            'client_secret': '***hidden***',
            'expires_at': tokens.get('expires_at'),
        }

        print(json.dumps(safe_display, indent=2))

        # Save to file
        output_file = f"/tmp/{provider_type}_credentials.json"
        with open(output_file, 'w') as f:
            json.dump(tokens, f, indent=2)

        print(f"\n✅ Full credentials saved to: {output_file}")
        print("\n⚠️  SECURITY NOTES:")
        print("  1. Never commit credentials to git")
        print("  2. Encrypt before storing in database")
        print("  3. Delete the credentials file after use")
        print("  4. The refresh_token is especially sensitive\n")

        # Provide next steps
        print("─"*60)
        print("Next Steps:")
        print("─"*60)
        print("\n1. Create email account via API:")
        print(f"""
   curl -X POST http://localhost:8000/email-accounts/ \\
     -H "Authorization: Bearer YOUR_TOKEN" \\
     -H "Content-Type: application/json" \\
     -d @{output_file}
        """)

        print("\n2. Or update existing account:")
        print(f"""
   curl -X PATCH http://localhost:8000/email-accounts/{{account_id}} \\
     -H "Authorization: Bearer YOUR_TOKEN" \\
     -H "Content-Type: application/json" \\
     -d '{{"credentials": {{...credentials from {output_file}...}}}}'
        """)

        print("\n3. Test sync:")
        print("""
   curl -X POST http://localhost:8000/email-accounts/{account_id}/sync \\
     -H "Authorization: Bearer YOUR_TOKEN" \\
     -d '{"incremental": false}'
        """)

    except Exception as e:
        print(f"\n❌ Failed to exchange code for tokens: {e}")
        sys.exit(1)


async def test_email_connection(provider_type: str, credentials: dict):
    """Test email connection with obtained credentials"""
    try:
        if provider_type == 'gmail':
            from integrations.email.providers.gmail_provider import GmailProvider
            from integrations.email.protocols import EmailProviderConfig

            config = EmailProviderConfig(
                provider_type='gmail',
                email_address='test@gmail.com',
                credentials=credentials,
                connection_params={}
            )

            provider = GmailProvider()
            await provider.connect(config)

            # Try to fetch profile
            profile = provider._service.users().getProfile(userId='me').execute()

            print(f"✅ Successfully connected to Gmail!")
            print(f"   Email: {profile.get('emailAddress')}")
            print(f"   Total Messages: {profile.get('messagesTotal')}")

            await provider.disconnect()

        elif provider_type == 'outlook':
            print("⚠️  Outlook connection test not implemented yet")
            print("   Credentials obtained successfully - test manually")

        else:
            print(f"⚠️  Connection test not implemented for {provider_type}")
            print("   Credentials obtained successfully - test manually")

    except Exception as e:
        print(f"⚠️  Connection test failed: {e}")
        print("   Credentials obtained but couldn't verify connection")
        print("   This might be due to API configuration issues")


def get_console_url(provider_type: str) -> str:
    """Get provider console URL for getting client credentials"""
    urls = {
        'gmail': 'https://console.cloud.google.com/apis/credentials',
        'outlook': 'https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade',
        'yahoo': 'https://developer.yahoo.com/apps/'
    }
    return urls.get(provider_type, 'your provider console')


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="OAuth Setup Wizard for Email Providers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup Gmail OAuth
  python scripts/oauth_setup_wizard.py --provider gmail

  # Setup Outlook OAuth
  python scripts/oauth_setup_wizard.py --provider outlook

  # Setup with email hint
  python scripts/oauth_setup_wizard.py --provider gmail --email user@gmail.com
        """
    )

    parser.add_argument(
        '--provider',
        required=True,
        choices=list(OAUTH_PROVIDERS.keys()),
        help='Email provider (gmail, outlook, yahoo)'
    )

    parser.add_argument(
        '--email',
        help='Email address (optional, used as login hint)'
    )

    args = parser.parse_args()

    try:
        asyncio.run(run_oauth_flow(args.provider, args.email))
    except KeyboardInterrupt:
        print("\n\n❌ OAuth setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ OAuth setup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
