from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.enums import TenantStatus
from models.mixins import CuidMixin, TimestampMixin


class Tenant(CuidMixin, TimestampMixin, Base):
    """
    Root tenant entity for multi-tenant architecture.

    Note: Tenant does not have a tenant_id since it is the root of the hierarchy.
    Uses CuidMixin and TimestampMixin only (no TenantMixin).
    """

    __tablename__ = "tenant"

    # Business fields
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=TenantStatus.ACTIVE.value, index=True
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN {tuple(TenantStatus.values())}", name="tenant_status_check"
        ),
    )
