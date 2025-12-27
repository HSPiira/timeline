from sqlalchemy import Column, Index, String

from core.database import Base
from models.mixins import MultiTenantModel


class Subject(MultiTenantModel, Base):
    """
    Subject entity representing people, organizations, or entities involved in events.

    Inherits from MultiTenantModel:
        - id: CUID primary key
        - tenant_id: Foreign key to tenant
        - created_at: Creation timestamp
        - updated_at: Last update timestamp
    """

    __tablename__ = "subject"

    # Business fields
    subject_type = Column(String, nullable=False, index=True)
    external_ref = Column(String, index=True)

    __table_args__ = (Index("ix_subject_tenant_type", "tenant_id", "subject_type"),)
