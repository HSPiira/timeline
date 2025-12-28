"""OAuth provider configuration model with versioning and envelope encryption"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from models.mixins import AuditedMultiTenantModel


class OAuthProviderConfig(AuditedMultiTenantModel, Base):
    """
    OAuth provider client credentials with versioning support.

    Inherits from AuditedMultiTenantModel:
        - id, tenant_id: Multi-tenant isolation
        - created_at, updated_at: Timestamps
        - created_by, updated_by: Audit trail
        - deleted_at, deleted_by: Soft delete
        - audit_metadata: Additional audit context

    Versioning Strategy:
        - Each credential rotation creates a new version
        - Existing EmailAccounts remain bound to their creation version
        - Allows seamless credential rotation without breaking active integrations
    """

    __tablename__ = "oauth_provider_config"

    # Provider identification
    provider_type: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # gmail, outlook, yahoo
    display_name: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "Gmail", "Microsoft 365"

    # Version management
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )  # Incremented on credential rotation
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )  # Current version flag
    superseded_by_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # Points to newer version

    # Envelope encryption (master key managed externally)
    # Format: {kms_key_id}:{encrypted_data}
    client_id_encrypted: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Encrypted with envelope key
    client_secret_encrypted: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Encrypted with envelope key
    encryption_key_id: Mapped[str] = mapped_column(
        String, nullable=False
    )  # References external KMS key

    # OAuth configuration
    redirect_uri: Mapped[str] = mapped_column(
        String, nullable=False
    )  # Must match provider console
    redirect_uri_whitelist: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )  # Allowed redirect URIs

    # Scope management
    allowed_scopes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False
    )  # All scopes available from provider
    default_scopes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False
    )  # Default scopes for new connections
    tenant_configured_scopes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False
    )  # Tenant-specific scope restrictions

    # Provider metadata
    authorization_endpoint: Mapped[str] = mapped_column(String, nullable=False)
    token_endpoint: Mapped[str] = mapped_column(String, nullable=False)
    provider_metadata: Mapped[dict[str, str] | None] = mapped_column(
        JSON, nullable=True
    )  # Additional provider config

    # Health and status tracking
    health_status: Mapped[str] = mapped_column(
        String, nullable=False, default="unknown"
    )  # healthy, degraded, unhealthy, unknown
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rate limiting (connections per hour)
    rate_limit_connections_per_hour: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=10
    )
    current_hour_connections: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    rate_limit_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # One active config per provider per tenant (allows multiple versions)
        UniqueConstraint(
            "tenant_id",
            "provider_type",
            "version",
            name="uq_tenant_provider_version",
        ),
        # Index for finding active configs
        Index(
            "ix_oauth_provider_config_active",
            "tenant_id",
            "provider_type",
            "is_active",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<OAuthProviderConfig(id={self.id}, provider={self.provider_type}, "
            f"version={self.version}, active={self.is_active})>"
        )


class OAuthState(Base):
    """
    OAuth state parameter with signing and expiration.

    Used for CSRF protection and request correlation during OAuth flows.
    State is signed, time-bound, and replay-protected.
    """

    __tablename__ = "oauth_state"

    # CUID primary key (also used as state parameter)
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # Context information
    tenant_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # For tenant isolation
    user_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # User initiating OAuth
    provider_config_id: Mapped[str] = mapped_column(
        String, nullable=False
    )  # Which config was used

    # Security
    nonce: Mapped[str] = mapped_column(String, nullable=False)  # Cryptographic nonce
    signature: Mapped[str] = mapped_column(
        String, nullable=False
    )  # HMAC signature of payload
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )  # 10 minute TTL

    # Tracking
    consumed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )  # Replay protection
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    callback_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Return URL (optional, for frontend redirects after OAuth)
    return_url: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        # Index for expiration cleanup
        Index("ix_oauth_state_expires", "expires_at", "consumed"),
    )

    def __repr__(self) -> str:
        return (
            f"<OAuthState(id={self.id}, user={self.user_id}, "
            f"consumed={self.consumed}, expires={self.expires_at})>"
        )


class OAuthAuditLog(Base):
    """
    Audit log for OAuth provider configuration changes.

    Tracks all create, update, disable, delete operations for compliance.
    """

    __tablename__ = "oauth_audit_log"

    # CUID primary key
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # Context
    tenant_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # For tenant isolation
    provider_config_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # Config being modified
    actor_user_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # Who made the change

    # Action details
    action: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # create, update, disable, delete, rotate
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Change tracking
    changes: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False
    )  # {field: {old: ..., new: ...}}
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # Optional reason

    # Request metadata
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        # Index for audit queries
        Index("ix_oauth_audit_tenant_time", "tenant_id", "timestamp"),
        Index("ix_oauth_audit_config_time", "provider_config_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<OAuthAuditLog(id={self.id}, action={self.action}, "
            f"actor={self.actor_user_id}, time={self.timestamp})>"
        )
