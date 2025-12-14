from core.protocols import IEventRepository, IHashService
from schemas.event import EventCreate


class EventService:
    """Event service following DIP - depends on abstractions, not concretions"""

    def __init__(self, event_repo: IEventRepository, hash_service: IHashService):
        self.event_repo = event_repo
        self.hash_service = hash_service

    async def create_event(self, tenant_id: str, data: EventCreate):
        """Create a new event with cryptographic chaining"""
        # Get previous hash for this subject within the tenant
        prev_hash = await self.event_repo.get_last_hash(data.subject_id, tenant_id)

        # Compute event hash
        event_hash = self.hash_service.compute_hash(
            tenant_id,
            data.subject_id,
            data.event_type,
            data.event_time,
            data.payload,
            prev_hash,
        )

        # Create event with hash
        return await self.event_repo.create_event(tenant_id, data, event_hash, prev_hash)