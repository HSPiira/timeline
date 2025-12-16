from sqlalchemy import Boolean, Column, Index, String, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.sql import func
from core.database import Base
from utils.generators import generate_cuid

class Permission(Base):
    """Granular permissions (e.g., 'event:create', 'subject:read')"""
    __tablename__ = "permission"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)

    #Permission structure: resource:action
    code = Column(String, nullable=False)  # e.g., 'event:create', 'subject:read'
    resource = Column(String, nullable=False, index=True)  # e.g., 'event', 'subject'
    action = Column(String, nullable=False, index=True)  # e.g., 'create', 'read', 'update', 'delete'
    description = Column(Text, nullable=True)  # Optional description

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_permission_tenant_code"),
        Index("ix_permission_resource_action", "tenant_id", "resource", "action"),
    )


class RolePermission(Base):
    """Many-to-many: roles ←→ permissions"""
    __tablename__ = "role_permission"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(String, ForeignKey("role.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(String, ForeignKey("permission.id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        Index("ix_role_permission_lookup", "tenant_id", "role_id"),
    )

class UserRole(Base):
    """Many-to-many: users ←→ roles"""
    __tablename__ = "user_role"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(String, ForeignKey("role.id", ondelete="CASCADE"), nullable=False)

    #Optional: role assignment metadata
    assigned_by = Column(String, ForeignKey("user.id"), nullable=True)  # Who assigned the role
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())  # When the role was assigned
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration time

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        Index("ix_user_role_lookup", "tenant_id", "user_id"),
    )