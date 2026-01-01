from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.permission import (
    Permission,
    RolePermission,
    UserRole,
)
from src.infrastructure.persistence.repositories.base import BaseRepository


class PermissionRepository(BaseRepository[Permission]):
    """Repository for Permission operations"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Permission)

    async def get_by_code_and_tenant(
        self, code: str, tenant_id: str
    ) -> Permission | None:
        """Get permission by code within a specific tenant"""
        result = await self.db.execute(
            select(Permission).where(
                Permission.code == code, Permission.tenant_id == tenant_id
            )
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

    async def get_permissions_for_role(
        self, role_id: str, tenant_id: str
    ) -> list[Permission]:
        """Get all permissions assigned to a role"""
        result = await self.db.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(
                RolePermission.role_id == role_id, RolePermission.tenant_id == tenant_id
            )
        )
        return list(result.scalars().all())

    async def assign_permission_to_role(
        self, role_id: str, permission_id: str, tenant_id: str
    ) -> RolePermission:
        """Assign a permission to a role"""
        role_permission = RolePermission(
            tenant_id=tenant_id, role_id=role_id, permission_id=permission_id
        )
        self.db.add(role_permission)
        await self.db.flush()
        await self.db.refresh(role_permission)
        return role_permission

    async def remove_permission_from_role(
        self, role_id: str, permission_id: str
    ) -> bool:
        """Remove a permission from a role"""
        result = await self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
        role_permission = result.scalar_one_or_none()

        if not role_permission:
            return False

        await self.db.delete(role_permission)
        await self.db.flush()
        return True

    async def assign_role_to_user(
        self,
        user_id: str,
        role_id: str,
        tenant_id: str,
        assigned_by: str | None = None,
    ) -> UserRole:
        """Assign a role to a user"""
        user_role = UserRole(
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=role_id,
            assigned_by=assigned_by,
        )
        self.db.add(user_role)
        await self.db.flush()
        await self.db.refresh(user_role)
        return user_role

    async def remove_role_from_user(self, user_id: str, role_id: str) -> bool:
        """Remove a role from a user"""
        result = await self.db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role_id
            )
        )
        user_role = result.scalar_one_or_none()

        if not user_role:
            return False

        await self.db.delete(user_role)
        await self.db.flush()
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
