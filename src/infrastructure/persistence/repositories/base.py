from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository implementing common CRUD operations (LSP)"""

    def __init__(self, db: AsyncSession, model: type[ModelType]):
        self.db = db
        self.model = model

    async def get_by_id(self, id: str) -> ModelType | None:
        """Get a single record by ID"""
        # Cast to Any for SQLAlchemy dynamic attribute access (id comes from CuidMixin)
        model: Any = self.model
        result = await self.db.execute(select(self.model).where(model.id == id))
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """Get all records with pagination"""
        result = await self.db.execute(select(self.model).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def create(self, obj: ModelType) -> ModelType:
        """Create a new record"""
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: ModelType) -> ModelType:
        """Update an existing record"""
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        """Delete a record"""
        await self.db.delete(obj)
        await self.db.flush()
