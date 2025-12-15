from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from core.database import Base
from utils.generators import generate_cuid


class Subject(Base):
    __tablename__ = "subject"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id"), nullable=False, index=True)
    subject_type = Column(String, nullable=False, index=True)
    external_ref = Column(String, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_subject_tenant_type', 'tenant_id', 'subject_type'),
    )