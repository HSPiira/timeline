"""Pydantic schemas for email account management"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class EmailAccountCreate(BaseModel):
    """Schema for creating an email account"""

    provider_type: str  # gmail, outlook, imap, icloud, yahoo
    email_address: str
    credentials: dict[str, Any]  # Will be encrypted before storage
    connection_params: dict[str, Any] | None = None

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        supported = ["gmail", "outlook", "imap", "icloud", "yahoo"]
        if v.lower() not in supported:
            raise ValueError(f"Provider type must be one of: {supported}. Got: {v}")
        return v.lower()

    @field_validator("email_address")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v.lower()


class EmailAccountUpdate(BaseModel):
    """Schema for updating an email account"""

    credentials: dict[str, Any] | None = None
    connection_params: dict[str, Any] | None = None
    is_active: bool | None = None


class EmailAccountResponse(BaseModel):
    """Schema for email account responses (credentials excluded)"""

    id: str
    tenant_id: str
    subject_id: str
    provider_type: str
    email_address: str
    connection_params: dict[str, Any] | None
    last_sync_at: datetime | None
    webhook_id: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # OAuth status fields
    oauth_status: str | None = None  # active, consent_denied, refresh_failed, revoked, expired, unknown
    oauth_error_count: int = 0
    oauth_next_retry_at: datetime | None = None
    last_auth_error: str | None = None
    last_auth_error_at: datetime | None = None
    token_last_refreshed_at: datetime | None = None
    granted_scopes: list[str] | None = None

    # Sync status tracking
    sync_status: str = "idle"  # idle, running, completed, failed
    sync_started_at: datetime | None = None
    sync_completed_at: datetime | None = None
    sync_messages_fetched: int = 0
    sync_events_created: int = 0
    sync_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SyncStatusResponse(BaseModel):
    """Schema for sync status endpoint"""

    account_id: str
    email_address: str
    status: str  # idle, running, completed, failed
    started_at: datetime | None
    completed_at: datetime | None
    messages_fetched: int
    events_created: int
    error: str | None
    duration_seconds: float | None = None


class EmailSyncRequest(BaseModel):
    """Schema for triggering email sync"""

    incremental: bool = True


class EmailSyncResponse(BaseModel):
    """Schema for sync operation results"""

    messages_fetched: int
    events_created: int
    provider: str
    sync_type: str


class WebhookSetupRequest(BaseModel):
    """Schema for webhook setup"""

    callback_url: str
