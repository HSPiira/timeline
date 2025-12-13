from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean, Index, BigInteger
from sqlalchemy.sql import func
from core.database import Base
from utils.generators import generate_cuid


class Document(Base):
    __tablename__ = "document"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id"), nullable=False, index=True)
    subject_id = Column(String, ForeignKey("subject.id"), nullable=False, index=True)
    event_id = Column(String, ForeignKey("event.id"), nullable=True, index=True)

    # Classification
    document_type = Column(String, nullable=False, index=True)

    # File metadata
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    file_size = Column(BigInteger, nullable=False)
    checksum = Column(String, nullable=False, index=True)  # SHA-256 for integrity

    # Storage
    storage_ref = Column(String, nullable=False)  # Path in S3/storage system

    # Versioning
    version = Column(Integer, nullable=False, default=1)
    parent_document_id = Column(String, ForeignKey("document.id"), nullable=True)
    is_latest_version = Column(Boolean, nullable=False, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String, nullable=True)  # User ID
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('ix_document_tenant_subject', 'tenant_id', 'subject_id'),
        Index('ix_document_checksum_unique', 'tenant_id', 'checksum', unique=True),
        Index('ix_document_versions', 'parent_document_id', 'version'),
    )
