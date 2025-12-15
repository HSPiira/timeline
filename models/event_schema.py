from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, JSON, UniqueConstraint
from sqlalchemy.sql import func
from core.database import Base
from utils.generators import generate_cuid


class EventSchema(Base):
    """Event schema model for tenant-specific payload validation"""
    __tablename__ = "event_schema"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    schema_json = Column(JSON, nullable=False)
    version = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "event_type", "version", name="uq_tenant_event_type_version"),
    )
