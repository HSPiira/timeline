from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, JSON, UniqueConstraint
from sqlalchemy.sql import func
from core.database import Base
from utils.generators import generate_cuid


class EventSchema(Base):
    """
    Event schema model for tenant-specific payload validation.

    Immutable versioning: Once created, schema_definition cannot be changed.
    Evolution happens through new versions with incremented version numbers.
    """
    __tablename__ = "event_schema"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    schema_definition = Column(JSON, nullable=False)  # Immutable after creation
    version = Column(Integer, nullable=False)  # Auto-incremented per event_type
    is_active = Column(Boolean, nullable=False, default=False)  # Must be explicitly activated
    created_by = Column(String, ForeignKey("user.id"), nullable=True)  # Audit trail

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "event_type", "version", name="uq_tenant_event_type_version"),
    )
