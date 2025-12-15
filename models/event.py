from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Index
from sqlalchemy.sql import func
from core.database import Base
from utils.generators import generate_cuid


class Event(Base):
    __tablename__ = "event"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id"), nullable=False, index=True)
    subject_id = Column(String, ForeignKey("subject.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    event_time = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=False)
    previous_hash = Column(String)
    hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_event_subject_time', 'subject_id', 'event_time'),
        Index('ix_event_tenant_subject', 'tenant_id', 'subject_id'),
    )