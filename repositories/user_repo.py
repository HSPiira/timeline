import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from models.user import User
from repositories.base import BaseRepository
from core.auth import get_password_hash, verify_password


class UserRepository(BaseRepository[User]):
    """Repository for User operations (SRP - data access only)"""

    def __init__(self, db: AsyncSession):
        super().__init__(db, User)

    async def get_by_username_and_tenant(
        self, username: str, tenant_id: str
    ) -> Optional[User]:
        """Get user by username within a specific tenant"""
        result = await self.db.execute(
            select(User).where(
                User.username == username,
                User.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_email_and_tenant(self, email: str, tenant_id: str) -> Optional[User]:
        """Get user by email within a specific tenant"""
        result = await self.db.execute(
            select(User).where(
                User.email == email,
                User.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    async def authenticate(
        self, username: str, tenant_id: str, password: str
    ) -> Optional[User]:
        """
        Authenticate user by username, tenant, and password.

        Returns User if credentials are valid, None otherwise.
        """
        user = await self.get_by_username_and_tenant(username, tenant_id)

        if not user:
            # Perform dummy hash check to prevent timing attacks
            verify_password(password, "$2b$12$dummy.hash.to.prevent.timing.attacks")
            return None

        if not user.is_active:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        return user

    async def create_user(
        self, tenant_id: str, username: str, email: str, password: str
    ) -> User:
        """Create a new user with hashed password"""
        hashed = await asyncio.to_thread(get_password_hash, password) 
        user = User(
            tenant_id=tenant_id,
            username=username,
            email=email,
            hashed_password=hashed,
            is_active=True
        )
        return await self.create(user)

    async def update_password(self, user_id: str, new_password: str) -> Optional[User]:
        """Update user password"""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.hashed_password = get_password_hash(new_password)
        return await self.update(user)

    async def deactivate(self, user_id: str) -> Optional[User]:
        """Deactivate user account"""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.is_active = "false"
        return await self.update(user)

    async def activate(self, user_id: str) -> Optional[User]:
        """Activate user account"""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.is_active = "true"
        return await self.update(user)

    async def get_users_by_tenant(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> list[User]:
        """Get all users for a tenant"""
        result = await self.db.execute(
            select(User)
            .where(User.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())
