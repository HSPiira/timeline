from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from core.database import Base
import datetime as dt

from utils.generators import generate_cuid


class Event(Base):
    __tablename__ = "event"


    id = Column(primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id"))
    subject_id = Column(String, ForeignKey("subject.id"))
    event_type = Column(String, nullable=False)
    event_time = Column(DateTime, nullable=False)
    payload = Column(JSON, nullable=False)
    previous_hash = Column(String)
    hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=dt.timezone.utc)