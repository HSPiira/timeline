"""Pydantic schemas for OAuth provider configuration API"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OAuthProviderConfigCreate(BaseModel):
    """Schema for creating OAuth provider configuration"""

    provider_type: str = Field(..., description="Provider identifier (gmail, outlook, yahoo)")
    client_id: str = Field(..., description="OAuth client ID from provider console")
    client_secret: str = Field(..., description="OAuth client secret from provider console")
    redirect_uri: str = Field(..., description="OAuth redirect URI (must match provider console)")
    scopes: list[str] | None = Field(
        None, description="Custom scopes (uses provider defaults if not specified)"
    )

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        supported = ["gmail", "outlook", "yahoo"]
        if v.lower() not in supported:
            raise ValueError(f"Provider type must be one of: {supported}. Got: {v}")
        return v.lower()

    @field_validator("redirect_uri")
    @classmethod
    def validate_redirect_uri(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("Redirect URI must start with http:// or https://")
        return v


class OAuthProviderConfigUpdate(BaseModel):
    """Schema for updating OAuth provider configuration"""

    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    scopes: list[str] | None = None
    is_active: bool | None = None
    rate_limit_connections_per_hour: int | None = None

    @field_validator("redirect_uri")
    @classmethod
    def validate_redirect_uri(cls, v: str | None) -> str | None:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("Redirect URI must start with http:// or https://")
        return v


class OAuthProviderConfigResponse(BaseModel):
    """Schema for OAuth provider configuration responses (secrets excluded)"""

    id: str
    tenant_id: str
    provider_type: str
    display_name: str
    version: int
    is_active: bool
    superseded_by_id: str | None
    redirect_uri: str
    redirect_uri_whitelist: list[str]
    allowed_scopes: list[str]
    default_scopes: list[str]
    tenant_configured_scopes: list[str]
    health_status: str
    last_health_check_at: datetime | None
    rate_limit_connections_per_hour: int | None
    current_hour_connections: int
    created_at: datetime
    updated_at: datetime
    created_by: str | None

    model_config = ConfigDict(from_attributes=True)


class OAuthProviderListResponse(BaseModel):
    """Schema for listing OAuth providers"""

    providers: list[OAuthProviderConfigResponse]
    total: int


class OAuthAuthorizeRequest(BaseModel):
    """Schema for initiating OAuth flow"""

    return_url: str | None = Field(None, description="URL to redirect user after OAuth completion")

    @field_validator("return_url")
    @classmethod
    def validate_return_url(cls, v: str | None) -> str | None:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("Return URL must start with http:// or https://")
        return v


class OAuthAuthorizeResponse(BaseModel):
    """Schema for OAuth authorization URL response"""

    auth_url: str = Field(..., description="URL to redirect user for OAuth consent")
    state: str = Field(..., description="OAuth state parameter (for callback)")
    expires_at: datetime = Field(..., description="When the state expires")
    provider: str = Field(..., description="Provider type")


class OAuthCallbackResponse(BaseModel):
    """Schema for OAuth callback response"""

    success: bool
    email_account_id: str
    email_address: str
    provider: str
    has_refresh_token: bool
    return_url: str | None = None


class OAuthProviderMetadata(BaseModel):
    """Schema for provider metadata"""

    provider_type: str
    provider_name: str
    authorization_endpoint: str
    token_endpoint: str
    supports_pkce: bool
    default_scopes: list[str]


class OAuthAuditLogResponse(BaseModel):
    """Schema for OAuth audit log responses"""

    id: str
    tenant_id: str
    provider_config_id: str
    actor_user_id: str
    action: str
    timestamp: datetime
    changes: dict[str, str]
    reason: str | None
    ip_address: str | None

    model_config = ConfigDict(from_attributes=True)


class OAuthProviderHealthCheck(BaseModel):
    """Schema for provider health check"""

    provider_type: str
    health_status: str
    last_check_at: datetime | None
    last_error: str | None
    is_operational: bool


class OAuthRotateCredentialsRequest(BaseModel):
    """Schema for rotating OAuth credentials"""

    new_client_id: str = Field(..., description="New OAuth client ID")
    new_client_secret: str = Field(..., description="New OAuth client secret")
    reason: str | None = Field(None, description="Reason for rotation")


class OAuthRotateCredentialsResponse(BaseModel):
    """Schema for credential rotation response"""

    old_version: int
    new_version: int
    provider_config_id: str
    migration_required: bool = Field(..., description="Whether existing connections need migration")
    affected_accounts: int = Field(..., description="Number of email accounts using old version")
