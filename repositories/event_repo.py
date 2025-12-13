from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from models.event import Event
from schemas.event import EventCreate


class EventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_last_hash(self, subject_id: str) -> str | None:
        """Get the hash of the most recent event for a subject"""
        result = await self.db.execute(
            select(Event.hash)
            .where(Event.subject_id == subject_id)
            .order_by(desc(Event.event_time))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
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
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def get_by_id(self, event_id: str) -> Event | None:
        result = await self.db.execute(
            select(Event).where(Event.id == event_id)
        )
        return result.scalar_one_or_none()

    async def get_by_subject(self, subject_id: str) -> list[Event]:
        """Get all events for a subject, ordered chronologically"""
        result = await self.db.execute(
            select(Event)
            .where(Event.subject_id == subject_id)
            .order_by(Event.event_time)
        )
        return list(result.scalars().all())
