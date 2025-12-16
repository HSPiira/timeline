from sqlalchemy import Boolean, Column, String, ForeignKey, DateTime, Text, UniqueConstraint, func
from core.database import Base
from utils.generators import generate_cuid

class Role(Base):
    """Tenant-scoped roles (e.g., 'admin', 'auditor', 'agent')"""
    __tablename__ = "role"
    
    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)

    #Role metadata
    code = Column(String, nullable=False) #e.g., 'admin', 'auditor', 'agent'
    name = Column(String, nullable=False) #Display name
    description = Column(Text, nullable=True) #Optional description
    is_system = Column(Boolean, nullable=False, default=False) #System roles cannot be modified or deleted
    is_active = Column(Boolean, nullable=False, default=True) #Soft delete flag

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('tenant_id', 'code', name='uq_role_tenant_code'),
    )