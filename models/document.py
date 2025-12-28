from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from models.mixins import MultiTenantModel


class Document(MultiTenantModel, Base):
    """
    Document entity for file storage and versioning.

    Inherits from MultiTenantModel:
        - id: CUID primary key
        - tenant_id: Foreign key to tenant
        - created_at: Creation timestamp
        - updated_at: Last update timestamp
    """

    __tablename__ = "document"

    subject_id: Mapped[str] = mapped_column(
        String, ForeignKey("subject.id"), nullable=False, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("event.id"), nullable=True, index=True
    )

    # Classification
    document_type: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # File metadata
    filename: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # SHA-256 for integrity

    # Storage
    storage_ref: Mapped[str] = mapped_column(
        String, nullable=False
    )  # Path in S3/storage system

    # Versioning
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_document_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("document.id"), nullable=True
    )
    is_latest_version: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # Additional audit fields (beyond MultiTenantModel)
    created_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    __table_args__ = (
        Index("ix_document_tenant_subject", "tenant_id", "subject_id"),
        Index("ix_document_checksum_unique", "tenant_id", "checksum", unique=True),
        Index(
            "ux_document_versions",
            "tenant_id",
            "subject_id",
            "parent_document_id",
            "version",
            unique=True,
        ),
    )
