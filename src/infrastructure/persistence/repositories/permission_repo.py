from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.permission import (
    Permission, RolePermission, UserRole)
from src.infrastructure.persistence.repositories.auditable_repo import AuditableRepository
from src.shared.enums import AuditAction

if TYPE_CHECKING:
    from src.application.services.system_audit_service import SystemAuditService


class PermissionRepository(AuditableRepository[Permission]):
    """Repository for Permission operations with automatic audit tracking."""

    def __init__(
        self,
        db: AsyncSession,
        audit_service: "SystemAuditService | None" = None,
        *,
        enable_audit: bool = True,
    ):
        super().__init__(db, Permission, audit_service, enable_audit=enable_audit)

    # Auditable implementation
    def _get_entity_type(self) -> str:
        return "permission"

    def _get_tenant_id(self, obj: Permission) -> str:
        return obj.tenant_id

    def _serialize_for_audit(self, obj: Permission) -> dict[str, Any]:
        return {
            "id": obj.id,
            "code": obj.code,
            "resource": obj.resource,
            "action": obj.action,
            "description": obj.description,
        }

    async def get_by_code_and_tenant(self, code: str, tenant_id: str) -> Permission | None:
        """Get permission by code within a specific tenant"""
        result = await self.db.execute(
            select(Permission).where(Permission.code == code, Permission.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> list[Permission]:
        """Get all permissions for a tenant"""
        result = await self.db.execute(
            select(Permission)
            .where(Permission.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .order_by(Permission.resource, Permission.action)
        )
        return list(result.scalars().all())

    async def get_by_resource(self, tenant_id: str, resource: str) -> list[Permission]:
        """Get all permissions for a specific resource"""
        result = await self.db.execute(
            select(Permission).where(
                Permission.tenant_id == tenant_id, Permission.resource == resource
            )
        )
        return list(result.scalars().all())

    async def get_permissions_for_role(self, role_id: str, tenant_id: str) -> list[Permission]:
        """Get all permissions assigned to a role"""
        result = await self.db.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id, RolePermission.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def assign_permission_to_role(
        self, role_id: str, permission_id: str, tenant_id: str
    ) -> RolePermission:
        """Assign a permission to a role with audit event."""
        role_permission = RolePermission(
            tenant_id=tenant_id, role_id=role_id, permission_id=permission_id
        )
        self.db.add(role_permission)
        await self.db.flush()
        await self.db.refresh(role_permission)

        # Emit custom audit for role assignment
        if self._audit_enabled and self.audit_service:
            await self.audit_service.emit_audit_event(
                tenant_id=tenant_id,
                entity_type="role",
                action=AuditAction.ASSIGNED,
                entity_id=role_id,
                entity_data={"permission_id": permission_id},
                metadata={"permission_assigned": permission_id},
            )

        return role_permission

    async def remove_permission_from_role(self, role_id: str, permission_id: str) -> bool:
        """Remove a permission from a role with audit event."""
        result = await self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
        role_permission = result.scalar_one_or_none()

        if not role_permission:
            return False

        tenant_id = role_permission.tenant_id

        await self.db.delete(role_permission)
        await self.db.flush()

        # Emit custom audit for role unassignment
        if self._audit_enabled and self.audit_service:
            await self.audit_service.emit_audit_event(
                tenant_id=tenant_id,
                entity_type="role",
                action=AuditAction.UNASSIGNED,
                entity_id=role_id,
                entity_data={"permission_id": permission_id},
                metadata={"permission_removed": permission_id},
            )

        return True

    async def assign_role_to_user(
        self,
        user_id: str,
        role_id: str,
        tenant_id: str,
        assigned_by: str | None = None,
    ) -> UserRole:
        """Assign a role to a user with audit event."""
        user_role = UserRole(
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=role_id,
            assigned_by=assigned_by,
        )
        self.db.add(user_role)
        await self.db.flush()
        await self.db.refresh(user_role)

        # Emit custom audit for role assignment to user
        if self._audit_enabled and self.audit_service:
            await self.audit_service.emit_audit_event(
                tenant_id=tenant_id,
                entity_type="role",
                action=AuditAction.ASSIGNED,
                entity_id=role_id,
                entity_data={"user_id": user_id, "assigned_by": assigned_by},
                metadata={"role_assigned_to_user": user_id},
            )

        return user_role

    async def remove_role_from_user(self, user_id: str, role_id: str) -> bool:
        """Remove a role from a user with audit event."""
        result = await self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        )
        user_role = result.scalar_one_or_none()

        if not user_role:
            return False

        tenant_id = user_role.tenant_id

        await self.db.delete(user_role)
        await self.db.flush()

        # Emit custom audit for role removal from user
        if self._audit_enabled and self.audit_service:
            await self.audit_service.emit_audit_event(
                tenant_id=tenant_id,
                entity_type="role",
                action=AuditAction.UNASSIGNED,
                entity_id=role_id,
                entity_data={"user_id": user_id},
                metadata={"role_removed_from_user": user_id},
            )

        return True

    async def get_user_roles(self, user_id: str, tenant_id: str) -> list:
        """Get all roles assigned to a user"""
        from src.infrastructure.persistence.models.role import Role

        result = await self.db.execute(
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                UserRole.tenant_id == tenant_id,
                Role.is_active.is_(True),
            )
        )
        return list(result.scalars().all())
