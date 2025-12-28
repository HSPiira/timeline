from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.role import Role
from repositories.base import BaseRepository


class RoleRepository(BaseRepository[Role]):
    """Repository for Role operations"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Role)

    async def get_by_code_and_tenant(self, code: str, tenant_id: str) -> Role | None:
        """Get role by code within a specific tenant"""
        result = await self.db.execute(
            select(Role).where(Role.code == code, Role.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> list[Role]:
        """Get all roles for a tenant"""
        query = select(Role).where(Role.tenant_id == tenant_id)

        if not include_inactive:
            query = query.where(Role.is_active.is_(True))

        query = query.offset(skip).limit(limit).order_by(Role.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def deactivate(self, role_id: str) -> Role | None:
        """Deactivate a role (soft delete)"""
        role = await self.get_by_id(role_id)
        if not role:
            return None

        role.is_active = False
        return await self.update(role)

    async def activate(self, role_id: str) -> Role | None:
        """Activate a role"""
        role = await self.get_by_id(role_id)
        if not role:
            return None

        role.is_active = True
        return await self.update(role)

    async def get_system_roles(self, tenant_id: str) -> list[Role]:
        """Get all system roles for a tenant"""
        result = await self.db.execute(
            select(Role).where(
                Role.tenant_id == tenant_id,
                Role.is_system.is_(True),
                Role.is_active.is_(True),
            )
        )
        return list(result.scalars().all())
