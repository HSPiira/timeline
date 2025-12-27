from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from models.event_schema import EventSchema
from repositories.base import BaseRepository
from typing import Optional, List


class EventSchemaRepository(BaseRepository[EventSchema]):
    """Repository for EventSchema entity"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, EventSchema)

    async def get_next_version(self, tenant_id: str, event_type: str) -> int:
        """Get the next version number for an event_type (auto-increment)"""
        result = await self.db.execute(
            select(func.max(EventSchema.version))
            .where(
                and_(
                    EventSchema.tenant_id == tenant_id,
                    EventSchema.event_type == event_type
                )
            )
        )
        max_version = result.scalar()
        return (max_version or 0) + 1

    async def get_active_schema(self, tenant_id: str, event_type: str) -> Optional[EventSchema]:
        """Get active schema for event type and tenant"""
        result = await self.db.execute(
            select(EventSchema)
            .where(
                and_(
                    EventSchema.tenant_id == tenant_id,
                    EventSchema.event_type == event_type,
                    EventSchema.is_active == True
                )
            )
            .order_by(EventSchema.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_version(
        self, tenant_id: str, event_type: str, version: int
    ) -> Optional[EventSchema]:
        """Get specific schema version"""
        result = await self.db.execute(
            select(EventSchema).where(
                and_(
                    EventSchema.tenant_id == tenant_id,
                    EventSchema.event_type == event_type,
                    EventSchema.version == version
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_all_for_event_type(
        self, tenant_id: str, event_type: str
    ) -> List[EventSchema]:
        """Get all schema versions for event type"""
        result = await self.db.execute(
            select(EventSchema)
            .where(
                and_(
                    EventSchema.tenant_id == tenant_id,
                    EventSchema.event_type == event_type
                )
            )
            .order_by(EventSchema.version.desc())
        )
        return list(result.scalars().all())

    async def get_all_for_tenant(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> List[EventSchema]:
        """Get all schemas for tenant with pagination"""
        result = await self.db.execute(
            select(EventSchema)
            .where(EventSchema.tenant_id == tenant_id)
            .order_by(EventSchema.event_type, EventSchema.version.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def deactivate_schema(self, schema_id: str) -> Optional[EventSchema]:
        """Deactivate a schema"""
        schema = await self.get_by_id(schema_id)
        if schema:
            schema.is_active = False
            return await self.update(schema)
        return None

    async def activate_schema(self, schema_id: str) -> Optional[EventSchema]:
        """Activate a schema"""
        schema = await self.get_by_id(schema_id)
        if schema:
            schema.is_active = True
            return await self.update(schema)
        return None
