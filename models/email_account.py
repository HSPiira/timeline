"""Email account model for integration metadata (NOT a core Timeline model)"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func
from core.database import Base


class EmailAccount(Base):
    """
    Email account configuration and credentials.

    This is integration metadata, NOT a core Timeline model.
    The actual email activity is stored as Timeline Events.
    """
    __tablename__ = "email_account"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenant.id"), nullable=False, index=True)
    subject_id = Column(String, ForeignKey("subject.id"), nullable=False, index=True)

    # Provider configuration
    provider_type = Column(String, nullable=False)  # gmail, outlook, imap, icloud, yahoo
    email_address = Column(String, nullable=False, index=True)

    # Encrypted credentials (Fernet)
    credentials_encrypted = Column(String, nullable=False)

    # Provider-specific connection parameters (IMAP server, ports, etc.)
    connection_params = Column(JSON, nullable=True)

    # Sync metadata
    last_sync_at = Column(DateTime, nullable=True)
    webhook_id = Column(String, nullable=True)  # For providers with webhook support
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<EmailAccount(id={self.id}, email={self.email_address}, provider={self.provider_type})>"
