from repositories.event_repo import EventRepository
from services.hash_service import HashService


class EventService:
    def __init__(self, repo: EventRepository):
        self.repo = repo


    def create_event(self, tenant_id, data):
        prev = self.repo.get_last_hash(data.subject_id)
        event_hash = HashService.compute(
            tenant_id,
            data.subject_id,
            data.event_type,
            data.event_time,
            data.payload,
            prev,
        )
        return self.repo.create(tenant_id, data, event_hash, prev)