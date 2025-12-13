from sqlalchemy import Column, String, DateTime, ForeignKey
from core.database import Base
import datetime as dt

from utils.generators import generate_cuid


class Subject(Base):
    __tablename__ = "subject"


    id = Column(primary_key=True, default=generate_cuid)
    tenant_id = Column(String, ForeignKey("tenant.id"))
    subject_type = Column(String, nullable=False)
    external_ref = Column(String)
    created_at = Column(DateTime, default=dt.timezone.utc)