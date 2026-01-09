from abc import ABC
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import object_session

from src.infrastructure.persistence.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(ABC, Generic[ModelType]):
    """
    Base repository implementing common CRUD operations (LSP).

    Provides cache invalidation hooks for subclasses to override.
    Subclasses should call super() methods to ensure proper lifecycle.
    """

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
        """Create a new record and trigger cache invalidation hook"""
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        await self._on_after_create(obj)
        return obj

    async def update(self, obj: ModelType) -> ModelType:
        """
        Update an existing record and trigger cache invalidation hook.

        Handles potentially detached objects by merging back to session.
        """
        # Merge object back to session if detached
        if object_session(obj) is None:
            obj = await self.db.merge(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        await self._on_after_update(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        """Delete a record and trigger cache invalidation hook"""
        await self._on_before_delete(obj)
        # delete() is synchronous for ORM objects in SQLAlchemy
        await self.db.delete(obj)
        await self.db.flush()

    # Cache invalidation hooks - override in subclasses
    async def _on_after_create(self, obj: ModelType) -> None:
        """Hook called after creating a record. Override to invalidate caches."""
        pass

    async def _on_after_update(self, obj: ModelType) -> None:
        """Hook called after updating a record. Override to invalidate caches."""
        pass

    async def _on_before_delete(self, obj: ModelType) -> None:
        """Hook called before deleting a record. Override to invalidate caches."""
        pass
