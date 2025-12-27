"""Pydantic schemas for document upload/download operations."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DocumentUploadResponse(BaseModel):
    """Response after successful document upload"""
    id: str
    subject_id: str
    event_id: Optional[str]
    document_type: str
    filename: str
    original_filename: str
    storage_ref: str
    checksum: str
    file_size: int
    mime_type: str
    version: int
    is_latest_version: bool
    created_at: datetime

    class Config:
        from_attributes = True
