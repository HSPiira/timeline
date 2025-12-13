from sqlalchemy import Column, String, DateTime
from core.database import Base
from utils.generators import generate_cuid
import datetime as dt

class Tenant(Base):
    __tablename__ = "tenant"

    id = Column(primary_key=True, default=generate_cuid)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=dt.timezone.utc)