"""Email account model for integration metadata (NOT a core Timeline model)"""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from models.mixins import MultiTenantModel


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
    connection_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    # Sync metadata
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    webhook_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # For providers with webhook support
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Token health monitoring (prevents re-authentication issues)
    token_last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    token_refresh_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_refresh_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    last_auth_error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_auth_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<EmailAccount(id={self.id}, email={self.email_address}, provider={self.provider_type})>"
