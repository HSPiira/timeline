"""Pydantic schemas for email account management"""
from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Dict, Any, Optional


class EmailAccountCreate(BaseModel):
    """Schema for creating an email account"""
    provider_type: str  # gmail, outlook, imap, icloud, yahoo
    email_address: str
    credentials: Dict[str, Any]  # Will be encrypted before storage
    connection_params: Optional[Dict[str, Any]] = None

    @field_validator('provider_type')
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        supported = ['gmail', 'outlook', 'imap', 'icloud', 'yahoo']
        if v.lower() not in supported:
            raise ValueError(
                f"Provider type must be one of: {supported}. Got: {v}"
            )
        return v.lower()

    @field_validator('email_address')
    @classmethod
    def validate_email(cls, v: str) -> str:
        if '@' not in v:
            raise ValueError("Invalid email address")
        return v.lower()


class EmailAccountUpdate(BaseModel):
    """Schema for updating an email account"""
    credentials: Optional[Dict[str, Any]] = None
    connection_params: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class EmailAccountResponse(BaseModel):
    """Schema for email account responses (credentials excluded)"""
    id: str
    tenant_id: str
    subject_id: str
    provider_type: str
    email_address: str
    connection_params: Optional[Dict[str, Any]]
    last_sync_at: Optional[datetime]
    webhook_id: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
