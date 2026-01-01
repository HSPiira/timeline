from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models.mixins import MultiTenantModel


class EventSchema(MultiTenantModel, Base):
    """
    Event schema model for tenant-specific payload validation.

    Inherits from MultiTenantModel:
        - id: CUID primary key
        - tenant_id: Foreign key to tenant
        - created_at: Creation timestamp
        - updated_at: Last update timestamp

    Immutable versioning: Once created, schema_definition cannot be changed.
    Evolution happens through new versions with incremented version numbers.
    """

    __tablename__ = "event_schema"

    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    schema_definition: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )  # Immutable after creation
    version: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Auto-incremented per event_type
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # Must be explicitly activated

    # Additional audit field (beyond MultiTenantModel)
    created_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "event_type", "version", name="uq_tenant_event_type_version"
        ),
    )
