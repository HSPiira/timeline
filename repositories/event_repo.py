from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from models.event import Event
from schemas.event import EventCreate
from repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    def __init__(self, db: AsyncSession):
        super().__init__(db, Event)

    async def get_last_hash(self, subject_id: str) -> str | None:
        """Get the hash of the most recent event for a subject"""
        result = await self.db.execute(
            select(Event.hash)
            .where(Event.subject_id == subject_id)
            .order_by(desc(Event.event_time))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_event(
        self,
        tenant_id: str,
        data: EventCreate,
        event_hash: str,
        previous_hash: str | None
    ) -> Event:
        """Create a new event with computed hash"""
        event = Event(
            tenant_id=tenant_id,
            subject_id=data.subject_id,
            event_type=data.event_type,
            event_time=data.event_time,
            payload=data.payload,
            hash=event_hash,
            previous_hash=previous_hash
        )
        return await self.create(event)

    async def get_by_subject(self, subject_id: str) -> list[Event]:
        """Get all events for a subject, ordered chronologically"""
        result = await self.db.execute(
            select(Event)
            .where(Event.subject_id == subject_id)
            .order_by(Event.event_time)
        )
        return list(result.scalars().all())
