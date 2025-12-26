from functools import lru_cache
from typing import Set
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.persmission import Permission, RolePermission, UserRole
from models.role import Role
from core.exceptions import PermissionDeniedError

class AuthorizationService:
    """
    Centralized permission checking with caching.
    Follow principle: "Check permissions, not roles"
    """

    def __init__(self, db: AsyncSession, cache_ttl: int = 300):
        self.db = db
        self.cache_ttl = cache_ttl
        

    async def get_user_permissions(self, user_id: str, tenant_id: str) -> Set[str]:
        """
        Get all permissions for a user (aggregated from all roles)
        Returns: Set of permission codes like {'event:create', 'subject:read'}
        """

        # Cache key: f"permissions:{tenant_id}:{user_id}"

        query = (
            select(Permission.code)
            .select_from(UserRole)
            .join(RolePermission, RolePermission.role_id == UserRole.role_id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id == user_id,
                UserRole.tenant_id == tenant_id,
                Role.is_active.is_(True),
                # Handle role expiration
                or_(UserRole.expires_at.is_(None), UserRole.expires_at > func.now())
            )
        )

        result = await self.db.execute(query)
        permissions = {row[0] for row in result.fetchall()}

        return permissions
    
    async def check_permission(
            self,
            user_id: str,
            tenant_id: str,
            resource: str,
            action: str
    ) -> bool:
        """
        Check if user has specific permission.
        
        Examples:
            - check_permission(user_id, tenant_id, "event", "create")
            - check_permission(user_id, tenant_id, "subject", "delete")
        """

        permissions = await self.get_user_permissions(user_id, tenant_id)

        # Check exact permission
        permission_code = f"{resource}:{action}"
        if permission_code in permissions:
            return True
        
        # Check wildcard permissions (optional enhancement)
        wildcard_resource = f"{resource}:*" # "event:*" grants all event actions
        wildcard_all = "*:*"  # Super admin wildcard

        return wildcard_resource in permissions or wildcard_all in permissions
    

    async def require_permission(
        self, 
        user_id: str, 
        tenant_id: str, 
        resource: str, 
        action: str
    ) -> None:
        """Raise exception if user lacks permission"""
        has_permission = await self.check_permission(user_id, tenant_id, resource, action)
        
        if not has_permission:
            raise PermissionDeniedError(
                f"User {user_id} lacks permission {resource}:{action}"
            )