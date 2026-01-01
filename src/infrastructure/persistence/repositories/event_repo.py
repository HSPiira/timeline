from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.event import Event
from src.infrastructure.persistence.repositories.base import BaseRepository
from src.presentation.api.v1.schemas.event import EventCreate


class EventRepository(BaseRepository[Event]):
    def __init__(self, db: AsyncSession):
        super().__init__(db, Event)

    async def get_last_hash(self, subject_id: str, tenant_id: str) -> str | None:
        """Get the hash of the most recent event for a subject within a tenant"""
        result = await self.db.execute(
            select(Event.hash)
            .where(Event.subject_id == subject_id)
            .where(Event.tenant_id == tenant_id)
            .order_by(desc(Event.event_time))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_last_event(self, subject_id: str, tenant_id: str) -> Event | None:
        """Get the most recent event for a subject within a tenant"""
        result = await self.db.execute(
            select(Event)
            .where(Event.subject_id == subject_id)
            .where(Event.tenant_id == tenant_id)
            .order_by(desc(Event.event_time))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_event(
        self,
        tenant_id: str,
        data: EventCreate,
        event_hash: str,
        previous_hash: str | None,
    ) -> Event:
        """Create a new event with computed hash and schema version"""
        event = Event(
            tenant_id=tenant_id,
            subject_id=data.subject_id,
            event_type=data.event_type,
            schema_version=data.schema_version,
            event_time=data.event_time,
            payload=data.payload,
            hash=event_hash,
            previous_hash=previous_hash,
        )
        return await self.create(event)

    async def get_by_subject(
        self, subject_id: str, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> list[Event]:
        """Get all events for a subject within a tenant, ordered newest-first"""
        result = await self.db.execute(
            select(Event)
            .where(Event.subject_id == subject_id)
            .where(Event.tenant_id == tenant_id)
            .order_by(Event.event_time.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_tenant(self, tenant_id: str, skip: int = 0, limit: int = 100) -> list[Event]:
        """Get all events for a tenant with pagination"""
        result = await self.db.execute(
            select(Event)
            .where(Event.tenant_id == tenant_id)
            .order_by(Event.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_type(
        self, tenant_id: str, event_type: str, skip: int = 0, limit: int = 100
    ) -> list[Event]:
        """Get all events of a specific type for a tenant"""
        result = await self.db.execute(
            select(Event)
            .where(Event.tenant_id == tenant_id, Event.event_type == event_type)
            .order_by(Event.event_time.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id_and_tenant(self, event_id: str, tenant_id: str) -> Event | None:
        """Get event by ID and verify it belongs to the tenant"""
        result = await self.db.execute(
            select(Event).where(Event.id == event_id, Event.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def count_by_schema_version(
        self, tenant_id: str, event_type: str, schema_version: int
    ) -> int:
        """Count events using a specific schema version"""
        result = await self.db.execute(
            select(func.count(Event.id)).where(
                Event.tenant_id == tenant_id,
                Event.event_type == event_type,
                Event.schema_version == schema_version,
            )
        )
        return result.scalar() or 0
