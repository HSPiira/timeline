from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models.mixins import MultiTenantModel


class Role(MultiTenantModel, Base):
    """
    Tenant-scoped roles (e.g., 'admin', 'auditor', 'agent').

    Inherits from MultiTenantModel:
        - id: CUID primary key
        - tenant_id: Foreign key to tenant
        - created_at: Creation timestamp
        - updated_at: Last update timestamp
    """

    __tablename__ = "role"

    # Role metadata
    code: Mapped[str] = mapped_column(
        String, nullable=False
    )  # e.g., 'admin', 'auditor', 'agent'
    name: Mapped[str] = mapped_column(String, nullable=False)  # Display name
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Optional description
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # System roles cannot be modified or deleted
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )  # Soft delete flag

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_role_tenant_code"),
    )
