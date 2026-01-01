from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models.mixins import CuidMixin, TenantMixin


class Permission(CuidMixin, TenantMixin, Base):
    """
    Granular permissions (e.g., 'event:create', 'subject:read').

    Inherits from:
        - CuidMixin: CUID primary key
        - TenantMixin: Tenant foreign key

    Note: Permissions are rarely modified, so no timestamps needed.
    """

    __tablename__ = "permission"

    # Permission structure: resource:action
    code: Mapped[str] = mapped_column(
        String, nullable=False
    )  # e.g., 'event:create', 'subject:read'
    resource: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., 'event', 'subject'
    action: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # e.g., 'create', 'read', 'update', 'delete'
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Optional description

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_permission_tenant_code"),
        Index("ix_permission_resource_action", "tenant_id", "resource", "action"),
    )


class RolePermission(CuidMixin, TenantMixin, Base):
    """
    Many-to-many: roles ←→ permissions.

    Inherits from:
        - CuidMixin: CUID primary key
        - TenantMixin: Tenant foreign key
    """

    __tablename__ = "role_permission"

    role_id: Mapped[str] = mapped_column(
        String, ForeignKey("role.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[str] = mapped_column(
        String, ForeignKey("permission.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        Index("ix_role_permission_lookup", "tenant_id", "role_id"),
    )


class UserRole(CuidMixin, TenantMixin, Base):
    """
    Many-to-many: users ←→ roles.

    Inherits from:
        - CuidMixin: CUID primary key
        - TenantMixin: Tenant foreign key
    """

    __tablename__ = "user_role"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        String, ForeignKey("role.id", ondelete="CASCADE"), nullable=False
    )

    # Role assignment metadata
    assigned_by: Mapped[str | None] = mapped_column(
        String, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        Index("ix_user_role_lookup", "tenant_id", "user_id"),
    )
