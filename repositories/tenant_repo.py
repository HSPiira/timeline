from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.tenant import Tenant
from repositories.base import BaseRepository
from typing import Optional, List


class TenantRepository(BaseRepository[Tenant]):
    """Repository for Tenant entity following LSP"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Tenant)

    async def get_by_code(self, code: str) -> Optional[Tenant]:
        """Get tenant by unique code"""
        result = await self.db.execute(
            select(Tenant).where(Tenant.code == code)
        )
        return result.scalar_one_or_none()

    async def get_active_tenants(self, skip: int = 0, limit: int = 100) -> List[Tenant]:
        """Get all active tenants with pagination"""
        result = await self.db.execute(
            select(Tenant)
            .where(Tenant.status == "active")
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(self, tenant_id: str, status: str) -> Optional[Tenant]:
        """Update tenant status"""
        tenant = await self.get_by_id(tenant_id)
        if tenant:
            tenant.status = status
            return await self.update(tenant)
        return None
