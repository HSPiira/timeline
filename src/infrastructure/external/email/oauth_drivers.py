"""OAuth provider driver abstraction with registry pattern"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import urlencode

import httpx

from src.shared.telemetry.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OAuthTokens:
    """Normalized OAuth token response"""

    access_token: str
    refresh_token: str | None
    token_type: str
    expires_in: int
    expires_at: datetime
    scope: str
    provider_metadata: dict[str, Any] | None = None


@dataclass
class OAuthUserInfo:
    """Normalized user information from provider"""

    email: str
    name: str | None = None
    picture: str | None = None
    provider_user_id: str | None = None
    provider_metadata: dict[str, Any] | None = None


class OAuthDriver(ABC):
    """
    Abstract base class for OAuth provider drivers.

    Each provider implements this interface to handle provider-specific:
    - Authorization URL generation
    - Token exchange
    - Token refresh
    - User info retrieval
    - PKCE support (if applicable)
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes

    # Subclasses should define these as class variables
    PROVIDER_NAME: ClassVar[str]
    PROVIDER_TYPE: ClassVar[str]
    AUTHORIZATION_ENDPOINT: ClassVar[str]
    TOKEN_ENDPOINT: ClassVar[str]
    SUPPORTS_PKCE: ClassVar[bool] = False

    @property
    def provider_name(self) -> str:
        """Human-readable provider name"""
        return self.PROVIDER_NAME

    @property
    def provider_type(self) -> str:
        """Provider identifier (gmail, outlook, yahoo)"""
        return self.PROVIDER_TYPE

    @property
    def authorization_endpoint(self) -> str:
        """OAuth authorization URL"""
        return self.AUTHORIZATION_ENDPOINT

    @property
    def token_endpoint(self) -> str:
        """OAuth token exchange URL"""
        return self.TOKEN_ENDPOINT

    @property
    def supports_pkce(self) -> bool:
        """Whether provider supports PKCE"""
        return self.SUPPORTS_PKCE

    def build_authorization_url(self, state: str, **extra_params: Any) -> str:
        """
        Build OAuth authorization URL.

        Args:
            state: CSRF protection token
            **extra_params: Provider-specific parameters

        Returns:
            Complete authorization URL for user redirect
        """
        params: dict[str, Any] = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            **self._get_authorization_params(),
            **extra_params,
        }

        return f"{self.authorization_endpoint}?{urlencode(params)}"

    @abstractmethod
    def _get_authorization_params(self) -> dict[str, Any]:
        """Provider-specific authorization parameters"""
        pass

    async def exchange_code_for_tokens(self, code: str, **extra_params: Any) -> OAuthTokens:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            **extra_params: Provider-specific parameters

        Returns:
            Normalized token response

        Raises:
            ValueError: If token exchange fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.token_endpoint,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                    **extra_params,
                },
            )

            if response.status_code != 200:
                logger.error(f"{self.provider_name} token exchange failed: {response.text}")
                raise ValueError(f"Token exchange failed: {response.status_code} {response.text}")

            token_data: dict[str, Any] = response.json()
            return self._normalize_token_response(token_data)

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token from initial authorization

        Returns:
            New tokens with potentially updated refresh token

        Raises:
            ValueError: If refresh fails
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_endpoint,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )

            if response.status_code != 200:
                logger.error(f"{self.provider_name} token refresh failed: {response.text}")
                raise ValueError(f"Token refresh failed: {response.status_code} {response.text}")

            token_data: dict[str, Any] = response.json()
            tokens = self._normalize_token_response(token_data)

            # Some providers don't return new refresh token - reuse existing
            if not tokens.refresh_token:
                tokens.refresh_token = refresh_token

            return tokens

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Retrieve user information using access token"""
        pass

    def _normalize_token_response(self, token_data: dict[str, Any]) -> OAuthTokens:
        """Normalize provider token response to standard format"""
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=expires_in,
            expires_at=expires_at,
            scope=token_data.get("scope", " ".join(self.scopes)),
            provider_metadata=token_data,
        )


class GmailDriver(OAuthDriver):
    """Gmail/Google OAuth driver"""

    PROVIDER_NAME = "Gmail"
    PROVIDER_TYPE = "gmail"
    AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

    def _get_authorization_params(self) -> dict[str, Any]:
        """Gmail-specific: access_type=offline, prompt=consent for refresh token"""
        return {
            "access_type": "offline",  # CRITICAL: Get refresh token
            "prompt": "consent",  # CRITICAL: Force consent for new refresh token
            "include_granted_scopes": "true",
        }

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user email from Google userinfo endpoint"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                raise ValueError(f"Failed to get user info: {response.text}")

            data: dict[str, Any] = response.json()
            return OAuthUserInfo(
                email=data["email"],
                name=data.get("name"),
                picture=data.get("picture"),
                provider_user_id=data.get("id"),
                provider_metadata=data,
            )


class OutlookDriver(OAuthDriver):
    """Microsoft Outlook/Office 365 OAuth driver"""

    PROVIDER_NAME = "Microsoft 365"
    PROVIDER_TYPE = "outlook"
    AUTHORIZATION_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    TOKEN_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

    def _get_authorization_params(self) -> dict[str, Any]:
        """Outlook-specific: response_mode, offline_access scope"""
        return {
            "response_mode": "query",
        }

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user email from Microsoft Graph"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                raise ValueError(f"Failed to get user info: {response.text}")

            data: dict[str, Any] = response.json()
            email = data.get("mail") or data.get("userPrincipalName")
            if not email:
                raise ValueError("Microsoft account has no email address configured")
            return OAuthUserInfo(
                email=email,
                name=data.get("displayName"),
                picture=None,  # Requires separate Graph call
                provider_user_id=data.get("id"),
                provider_metadata=data,
            )


class YahooDriver(OAuthDriver):
    """Yahoo Mail OAuth driver"""

    PROVIDER_NAME = "Yahoo Mail"
    PROVIDER_TYPE = "yahoo"
    AUTHORIZATION_ENDPOINT = "https://api.login.yahoo.com/oauth2/request_auth"
    TOKEN_ENDPOINT = "https://api.login.yahoo.com/oauth2/get_token"

    def _get_authorization_params(self) -> dict[str, Any]:
        """Yahoo-specific parameters"""
        return {}

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user email from Yahoo userinfo endpoint"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.login.yahoo.com/openid/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                raise ValueError(f"Failed to get user info: {response.text}")

            data: dict[str, Any] = response.json()
            return OAuthUserInfo(
                email=data["email"],
                name=data.get("name"),
                picture=data.get("picture"),
                provider_user_id=data.get("sub"),
                provider_metadata=data,
            )


class OAuthDriverRegistry:
    """
    Registry for OAuth provider drivers.

    Provides driver lookup and instantiation based on provider type.
    """

    _drivers: ClassVar[dict[str, type[OAuthDriver]]] = {
        "gmail": GmailDriver,
        "outlook": OutlookDriver,
        "yahoo": YahooDriver,
    }

    @classmethod
    def register(cls, provider_type: str, driver_class: type[OAuthDriver]) -> None:
        """Register a new OAuth driver"""
        cls._drivers[provider_type] = driver_class
        logger.info(f"Registered OAuth driver: {provider_type}")

    @classmethod
    def get_driver(
        cls,
        provider_type: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> OAuthDriver:
        """
        Get OAuth driver instance for provider.

        Args:
            provider_type: Provider identifier (gmail, outlook, yahoo)
            client_id: OAuth client ID
            client_secret: OAuth client secret
            redirect_uri: OAuth redirect URI
            scopes: List of OAuth scopes

        Returns:
            Initialized driver instance

        Raises:
            ValueError: If provider type not supported
        """
        if provider_type not in cls._drivers:
            raise ValueError(
                f"Unsupported provider: {provider_type}. "
                f"Supported: {', '.join(cls._drivers.keys())}"
            )

        driver_class = cls._drivers[provider_type]
        return driver_class(client_id, client_secret, redirect_uri, scopes)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider types"""
        return list(cls._drivers.keys())

    @classmethod
    def get_provider_metadata(cls, provider_type: str) -> dict[str, Any]:
        """Get provider metadata (name, endpoints, etc.)"""
        if provider_type not in cls._drivers:
            raise ValueError(f"Unknown provider: {provider_type}")

        driver_class = cls._drivers[provider_type]
        return {
            "provider_type": driver_class.PROVIDER_TYPE,
            "provider_name": driver_class.PROVIDER_NAME,
            "authorization_endpoint": driver_class.AUTHORIZATION_ENDPOINT,
            "token_endpoint": driver_class.TOKEN_ENDPOINT,
            "supports_pkce": driver_class.SUPPORTS_PKCE,
        }
