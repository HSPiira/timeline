"""Email account model for integration metadata (NOT a core Timeline model)"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models.mixins import MultiTenantModel


class EmailAccount(MultiTenantModel, Base):
    """
    Email account configuration and credentials.

    Inherits from MultiTenantModel:
        - id: CUID primary key
        - tenant_id: Foreign key to tenant
        - created_at: Creation timestamp
        - updated_at: Last update timestamp

    This is integration metadata, NOT a core Timeline model.
    The actual email activity is stored as Timeline Events.
    """

    __tablename__ = "email_account"

    subject_id: Mapped[str] = mapped_column(
        String, ForeignKey("subject.id"), nullable=False, index=True
    )

    # Provider configuration
    provider_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # gmail, outlook, imap, icloud, yahoo
    email_address: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Encrypted credentials (Fernet)
    credentials_encrypted: Mapped[str] = mapped_column(String, nullable=False)

    # Provider-specific connection parameters (IMAP server, ports, etc.)
    connection_params: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # OAuth integration tracking (for OAuth providers)
    oauth_provider_config_id: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )  # Which config version was used
    oauth_provider_config_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # Config version at connection time
    granted_scopes: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )  # Actual scopes user granted

    # Sync metadata
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # For providers with webhook support
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Sync status tracking (for background sync progress)
    sync_status: Mapped[str] = mapped_column(
        String, nullable=False, default="idle", index=True
    )  # idle, running, completed, failed
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_messages_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sync_events_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sync_error: Mapped[str | None] = mapped_column(String, nullable=True)

    # OAuth status tracking (enhanced failure handling)
    oauth_status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", index=True
    )  # active, consent_denied, refresh_failed, revoked, expired, unknown
    oauth_error_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # Consecutive errors
    oauth_next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Exponential backoff

    # Token health monitoring (prevents re-authentication issues)
    token_last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_refresh_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_refresh_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_auth_error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_auth_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EmailAccount(id={self.id}, "
            f"email={self.email_address}, "
            f"provider={self.provider_type})>"
        )
