from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from core.database import Base
from utils.generators import generate_cuid


class Tenant(Base):
    __tablename__ = "tenant"

    id = Column(String, primary_key=True, default=generate_cuid)
    code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(String, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())