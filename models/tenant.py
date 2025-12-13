from sqlalchemy import Column, String, DateTime, CheckConstraint
from sqlalchemy.sql import func
from core.database import Base
from core.enums import TenantStatus
from utils.generators import generate_cuid


class Tenant(Base):
    __tablename__ = "tenant"

    id = Column(String, primary_key=True, default=generate_cuid)
    code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default=TenantStatus.ACTIVE.value, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            f"status IN {tuple(TenantStatus.values())}",
            name='tenant_status_check'
        ),
    )