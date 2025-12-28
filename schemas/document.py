from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class DocumentCreate(BaseModel):
    """Schema for creating a document"""

    subject_id: str
    event_id: str | None = None
    document_type: str
    filename: str
    original_filename: str
    mime_type: str
    file_size: int
    checksum: str
    storage_ref: str
    created_by: str | None = None

    @field_validator("file_size")
    @classmethod
    def validate_file_size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("File size must be greater than 0")
        # 100MB max
        if v > 100 * 1024 * 1024:
            raise ValueError("File size cannot exceed 100MB")
        return v

    @field_validator("checksum")
    @classmethod
    def validate_checksum(cls, v: str) -> str:
        # SHA-256 produces 64 hex characters
        if len(v) != 64:
            raise ValueError("Checksum must be a valid SHA-256 hash (64 characters)")
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("Checksum must contain only hexadecimal characters")
        return v.lower()


class DocumentUpdate(BaseModel):
    """Schema for updating document metadata"""

    document_type: str | None = None


class DocumentResponse(BaseModel):
    """Schema for document responses"""

    id: str
    tenant_id: str
    subject_id: str
    event_id: str | None
    document_type: str
    filename: str
    original_filename: str
    mime_type: str
    file_size: int
    checksum: str
    storage_ref: str
    version: int
    parent_document_id: str | None
    is_latest_version: bool
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    deleted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
