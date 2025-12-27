"""Pydantic schemas for chain verification responses"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class EventVerificationResult(BaseModel):
    """Single event verification result"""
    event_id: str
    event_type: str
    event_time: datetime
    sequence: int
    is_valid: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    expected_hash: Optional[str] = None
    actual_hash: Optional[str] = None

    class Config:
        from_attributes = True


class ChainVerificationResponse(BaseModel):
    """Chain verification response for subject or tenant"""
    subject_id: Optional[str] = Field(None, description="Subject ID (null for tenant-wide)")
    tenant_id: str
    total_events: int
    valid_events: int
    invalid_events: int
    is_chain_valid: bool
    verified_at: datetime
    event_results: list[EventVerificationResult] = Field(default_factory=list)

    class Config:
        from_attributes = True
