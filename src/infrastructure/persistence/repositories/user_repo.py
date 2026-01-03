from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.user import User
from src.infrastructure.persistence.repositories.auditable_repo import AuditableRepository
from src.infrastructure.security.password import (get_password_hash,
                                                  verify_password)
from src.shared.enums import AuditAction

if TYPE_CHECKING:
    from src.application.services.system_audit_service import SystemAuditService


class UserRepository(AuditableRepository[User]):
    """Repository for User operations with automatic audit tracking."""

    def __init__(
        self,
        db: AsyncSession,
        audit_service: "SystemAuditService | None" = None,
        *,
        enable_audit: bool = True,
    ):
        super().__init__(db, User, audit_service, enable_audit=enable_audit)

    # Auditable implementation
    def _get_entity_type(self) -> str:
        return "user"

    def _get_tenant_id(self, obj: User) -> str:
        return obj.tenant_id

    def _serialize_for_audit(self, obj: User) -> dict[str, Any]:
        return {
            "id": obj.id,
            "username": obj.username,
            "email": obj.email,
            "is_active": obj.is_active,
            # Note: hashed_password is automatically redacted by SystemAuditService
        }

    async def get_by_username_and_tenant(self, username: str, tenant_id: str) -> User | None:
        """Get user by username within a specific tenant"""
        result = await self.db.execute(
            select(User).where(User.username == username, User.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email_and_tenant(self, email: str, tenant_id: str) -> User | None:
        """Get user by email within a specific tenant"""
        result = await self.db.execute(
            select(User).where(User.email == email, User.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant(self, user_id: str, tenant_id: str) -> User | None:
        """Get user by ID and verify it belongs to the tenant"""
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def authenticate(self, username: str, tenant_id: str, password: str) -> User | None:
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

    async def create_user(self, tenant_id: str, username: str, email: str, password: str) -> User:
        """Create a new user with hashed password"""
        hashed = await asyncio.to_thread(get_password_hash, password)
        user = User(
            tenant_id=tenant_id,
            username=username,
            email=email,
            hashed_password=hashed,
            is_active=True,
        )
        return await self.create(user)

    async def update_password(self, user_id: str, new_password: str) -> User | None:
        """Update user password"""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.hashed_password = get_password_hash(new_password)
        return await self.update(user)

    async def deactivate(self, user_id: str) -> User | None:
        """Deactivate user account with audit event."""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.is_active = False
        updated = await self.update(user)
        await self.emit_custom_audit(updated, AuditAction.DEACTIVATED)
        return updated

    async def activate(self, user_id: str) -> User | None:
        """Activate user account with audit event."""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.is_active = True
        updated = await self.update(user)
        await self.emit_custom_audit(updated, AuditAction.ACTIVATED)
        return updated

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
