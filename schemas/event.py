from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Any, Dict


class EventCreate(BaseModel):
    subject_id: str
    event_type: str
    event_time: datetime
    payload: Dict

class EventResponse(BaseModel):
    id: str
    tenant_id: str
    subject_id: str
    event_type: str
    event_time: datetime
    payload: Dict[str, Any]
    hash: str
    previous_hash: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)