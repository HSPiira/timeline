"""
Unified OAuth Manager for Email Providers

Handles OAuth 2.0 flows for multiple email providers with automatic token refresh
and proper configuration to prevent token expiration issues.

Supports: Gmail, Outlook, Yahoo, and other OAuth 2.0 providers.
"""

from typing import Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
import secrets
from authlib.integrations.requests_client import OAuth2Session
from authlib.oauth2.rfc6749 import OAuth2Token
from core.logging import get_logger

logger = get_logger(__name__)


class OAuthProvider:
    """OAuth provider configuration"""

    def __init__(
        self,
        name: str,
        authorization_endpoint: str,
        token_endpoint: str,
        scopes: list[str],
        extra_authorize_params: Optional[Dict] = None
    ):
        self.name = name
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.scopes = scopes
        self.extra_authorize_params = extra_authorize_params or {}


# Provider configurations
OAUTH_PROVIDERS = {
    'gmail': OAuthProvider(
        name='Gmail',
        authorization_endpoint='https://accounts.google.com/o/oauth2/v2/auth',
        token_endpoint='https://oauth2.googleapis.com/token',
        scopes=[
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.modify'
        ],
        extra_authorize_params={
            'access_type': 'offline',  # CRITICAL: Get refresh token
            'prompt': 'consent',        # CRITICAL: Force consent to get new refresh token
            'include_granted_scopes': 'true'
        }
    ),
    'outlook': OAuthProvider(
        name='Outlook/Office 365',
        authorization_endpoint='https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
        token_endpoint='https://login.microsoftonline.com/common/oauth2/v2.0/token',
        scopes=[
            'https://graph.microsoft.com/Mail.Read',
            'https://graph.microsoft.com/Mail.ReadWrite',
            'offline_access'  # Required for refresh token
        ],
        extra_authorize_params={
            'response_mode': 'query'
        }
    ),
    'yahoo': OAuthProvider(
        name='Yahoo Mail',
        authorization_endpoint='https://api.login.yahoo.com/oauth2/request_auth',
        token_endpoint='https://api.login.yahoo.com/oauth2/get_token',
        scopes=['mail-r', 'mail-w'],
        extra_authorize_params={}
    )
}


class UnifiedOAuthManager:
    """
    Unified OAuth 2.0 manager for email providers.

    Ensures tokens are obtained with proper settings to enable automatic refresh:
    - Gmail: access_type='offline', prompt='consent'
    - Outlook: offline_access scope
    - Yahoo: Proper token exchange

    Usage:
        manager = UnifiedOAuthManager('gmail', client_id, client_secret, redirect_uri)
        auth_url, state = await manager.get_authorization_url()
        # User authorizes, gets callback with code
        tokens = await manager.exchange_code_for_tokens(code, state)
        # Later, when access token expires:
        new_tokens = await manager.refresh_access_token(tokens['refresh_token'])
    """

    def __init__(
        self,
        provider_type: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str = 'http://localhost:8080/callback'
    ):
        """
        Initialize OAuth manager for a specific provider.

        Args:
            provider_type: Provider identifier ('gmail', 'outlook', 'yahoo')
            client_id: OAuth client ID from provider console
            client_secret: OAuth client secret from provider console
            redirect_uri: OAuth redirect URI (must match console configuration)
        """
        if provider_type not in OAUTH_PROVIDERS:
            raise ValueError(
                f"Unsupported provider: {provider_type}. "
                f"Supported providers: {', '.join(OAUTH_PROVIDERS.keys())}"
            )

        self.provider_type = provider_type
        self.provider_config = OAUTH_PROVIDERS[provider_type]
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

        logger.info(f"Initialized OAuth manager for {self.provider_config.name}")

    def get_authorization_url(self) -> Tuple[str, str]:
        """
        Generate OAuth authorization URL with proper parameters.

        Returns:
            Tuple of (authorization_url, state)
            - authorization_url: URL to redirect user to for consent
            - state: CSRF protection token (store and validate on callback)
        """
        # Generate cryptographically secure state parameter for CSRF protection
        state = secrets.token_urlsafe(32)

        # Build authorization parameters
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.provider_config.scopes),
            'state': state,
            **self.provider_config.extra_authorize_params
        }

        authorization_url = f"{self.provider_config.authorization_endpoint}?{urlencode(params)}"

        logger.info(
            f"Generated authorization URL for {self.provider_config.name} "
            f"with scopes: {', '.join(self.provider_config.scopes)}"
        )

        return authorization_url, state

    async def exchange_code_for_tokens(self, code: str, state: Optional[str] = None) -> Dict:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback
            state: State parameter from authorization URL (for validation)

        Returns:
            Dictionary with token information:
            {
                'access_token': str,
                'refresh_token': str,
                'token_type': 'Bearer',
                'expires_in': int (seconds),
                'expires_at': datetime,
                'scope': str
            }

        Raises:
            ValueError: If token exchange fails or refresh_token not returned
        """
        try:
            # Create OAuth session
            session = OAuth2Session(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=self.provider_config.scopes
            )

            # Exchange code for tokens
            token_response = session.fetch_token(
                url=self.provider_config.token_endpoint,
                code=code,
                grant_type='authorization_code'
            )

            # Validate response
            if 'access_token' not in token_response:
                raise ValueError("Token response missing access_token")

            if 'refresh_token' not in token_response:
                logger.warning(
                    f"⚠️  No refresh_token returned by {self.provider_config.name}. "
                    f"This means tokens will expire and user will need to re-authenticate. "
                    f"Ensure OAuth flow includes: access_type='offline' (Gmail), "
                    f"offline_access scope (Outlook)"
                )

            # Calculate expiration time
            expires_in = token_response.get('expires_in', 3600)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Build normalized token structure
            tokens = {
                'access_token': token_response['access_token'],
                'refresh_token': token_response.get('refresh_token'),
                'token_type': token_response.get('token_type', 'Bearer'),
                'expires_in': expires_in,
                'expires_at': expires_at.isoformat(),
                'scope': token_response.get('scope', ' '.join(self.provider_config.scopes)),
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }

            logger.info(
                f"✅ Successfully exchanged authorization code for tokens "
                f"(has_refresh_token: {bool(tokens['refresh_token'])})"
            )

            return tokens

        except Exception as e:
            logger.error(
                f"Failed to exchange authorization code for tokens: {e}",
                exc_info=True
            )
            raise ValueError(f"Token exchange failed: {e}") from e

    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token from initial authorization

        Returns:
            Dictionary with new token information (same structure as exchange_code_for_tokens)

        Raises:
            ValueError: If token refresh fails
        """
        if not refresh_token:
            raise ValueError("Refresh token is required")

        try:
            # Create OAuth session
            session = OAuth2Session(
                client_id=self.client_id,
                client_secret=self.client_secret
            )

            # Refresh token
            token_response = session.refresh_token(
                url=self.provider_config.token_endpoint,
                refresh_token=refresh_token
            )

            # Calculate expiration time
            expires_in = token_response.get('expires_in', 3600)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Build normalized token structure
            # Note: refresh_token might not be returned (some providers reuse the same one)
            tokens = {
                'access_token': token_response['access_token'],
                'refresh_token': token_response.get('refresh_token', refresh_token),  # Reuse if not returned
                'token_type': token_response.get('token_type', 'Bearer'),
                'expires_in': expires_in,
                'expires_at': expires_at.isoformat(),
                'scope': token_response.get('scope', ' '.join(self.provider_config.scopes)),
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }

            logger.info(f"✅ Successfully refreshed access token for {self.provider_config.name}")

            return tokens

        except Exception as e:
            logger.error(
                f"Failed to refresh access token: {e}. "
                f"Common causes: refresh token expired (6 months unused), "
                f"user revoked access, invalid client credentials",
                exc_info=True
            )
            raise ValueError(f"Token refresh failed: {e}") from e

    def validate_tokens(self, credentials: Dict) -> Tuple[bool, list[str]]:
        """
        Validate token structure and completeness.

        Args:
            credentials: Token dictionary to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Check required fields
        required_fields = ['access_token', 'client_id', 'client_secret']
        for field in required_fields:
            if not credentials.get(field):
                errors.append(f"Missing required field: {field}")

        # Check for refresh token (critical for auto-refresh)
        if not credentials.get('refresh_token'):
            errors.append(
                "Missing refresh_token - user will need to re-authenticate when access_token expires. "
                "Ensure OAuth flow uses access_type='offline' (Gmail) or offline_access scope (Outlook)"
            )

        # Check token expiration if present
        if 'expires_at' in credentials:
            try:
                expires_at = datetime.fromisoformat(credentials['expires_at'].replace('Z', '+00:00'))
                if expires_at < datetime.now(timezone.utc):
                    errors.append("Access token has expired - needs refresh")
            except Exception as e:
                errors.append(f"Invalid expires_at format: {e}")

        is_valid = len(errors) == 0

        if not is_valid:
            logger.warning(
                f"Token validation failed for {self.provider_config.name}: "
                f"{'; '.join(errors)}"
            )
        else:
            logger.info(f"✅ Tokens validated successfully for {self.provider_config.name}")

        return is_valid, errors

    def should_refresh_token(self, credentials: Dict) -> bool:
        """
        Check if access token should be refreshed proactively.

        Refreshes if token expires within 5 minutes (300 seconds).

        Args:
            credentials: Token dictionary with expires_at field

        Returns:
            True if token should be refreshed, False otherwise
        """
        if 'expires_at' not in credentials:
            # If no expiration info, assume it's expired
            return True

        try:
            expires_at = datetime.fromisoformat(credentials['expires_at'].replace('Z', '+00:00'))
            # Refresh if expires within 5 minutes
            should_refresh = expires_at < datetime.now(timezone.utc) + timedelta(minutes=5)

            if should_refresh:
                logger.info(
                    f"Proactively refreshing token (expires at {expires_at}, "
                    f"current time: {datetime.now(timezone.utc)})"
                )

            return should_refresh

        except Exception as e:
            logger.warning(f"Could not parse expires_at, assuming token should be refreshed: {e}")
            return True
