from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.tenant import Tenant


class TenantRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, tenant_id: str) -> Tenant | None:
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Tenant | None:
        result = await self.db.execute(
            select(Tenant).where(Tenant.code == code)
        )
        return result.scalar_one_or_none()

    async def create(self, tenant_data: dict) -> Tenant:
        tenant = Tenant(**tenant_data)
        self.db.add(tenant)
        await self.db.flush()
        return tenant
