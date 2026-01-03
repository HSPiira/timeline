"""
Tenant initialization service for setting up RBAC and default data.

This service is called when a new tenant is created to set up:
- Default permissions
- Default roles (admin, manager, agent, auditor)
- Role-permission assignments
"""
from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.permission import Permission, RolePermission, UserRole
from src.infrastructure.persistence.models.role import Role
from src.shared.utils.generators import generate_cuid


class RoleData(TypedDict):
    """Type definition for role configuration"""

    name: str
    description: str
    permissions: list[str]
    is_system: bool


# System permissions - standard set for all tenants
SYSTEM_PERMISSIONS = [
    # Event permissions
    ("event:create", "event", "create", "Create events"),
    ("event:read", "event", "read", "View event details"),
    ("event:list", "event", "list", "List events"),
    # Subject permissions
    ("subject:create", "subject", "create", "Create subjects"),
    ("subject:read", "subject", "read", "View subject details"),
    ("subject:update", "subject", "update", "Update subjects"),
    ("subject:delete", "subject", "delete", "Delete subjects"),
    ("subject:list", "subject", "list", "List subjects"),
    # User management
    ("user:create", "user", "create", "Create users"),
    ("user:read", "user", "read", "View users"),
    ("user:update", "user", "update", "Update users"),
    ("user:deactivate", "user", "deactivate", "Deactivate users"),
    ("user:list", "user", "list", "List users"),
    # Role management
    ("role:create", "role", "create", "Create roles"),
    ("role:read", "role", "read", "View roles"),
    ("role:update", "role", "update", "Modify roles"),
    ("role:delete", "role", "delete", "Delete roles"),
    ("role:assign", "role", "assign", "Assign roles to users"),
    # Permission management
    ("permission:create", "permission", "create", "Create permissions"),
    ("permission:read", "permission", "read", "View permissions"),
    ("permission:delete", "permission", "delete", "Delete permissions"),
    # Document permissions
    ("document:create", "document", "create", "Upload documents"),
    ("document:read", "document", "read", "View documents"),
    ("document:delete", "document", "delete", "Delete documents"),
    # Event schema permissions
    ("event_schema:create", "event_schema", "create", "Create event schemas"),
    ("event_schema:read", "event_schema", "read", "View event schemas"),
    ("event_schema:update", "event_schema", "update", "Update event schemas"),
    # Workflow permissions
    ("workflow:create", "workflow", "create", "Create workflows"),
    ("workflow:read", "workflow", "read", "View workflows"),
    ("workflow:update", "workflow", "update", "Update workflows"),
    ("workflow:delete", "workflow", "delete", "Delete workflows"),
    # Wildcard permissions
    ("*:*", "*", "*", "Super admin - all permissions"),
]


# Default roles with permission assignments
DEFAULT_ROLES: dict[str, RoleData] = {
    "admin": {
        "name": "Administrator",
        "description": "Full system access with all permissions",
        "permissions": ["*:*"],
        "is_system": True,
    },
    "manager": {
        "name": "Manager",
        "description": "Can manage events, subjects, and users",
        "permissions": [
            "event:*",
            "subject:*",
            "user:read",
            "user:create",
            "user:list",
            "document:*",
            "event_schema:read",
            "workflow:*",
        ],
        "is_system": True,
    },
    "agent": {
        "name": "Agent",
        "description": "Can create and view events and subjects",
        "permissions": [
            "event:create",
            "event:read",
            "event:list",
            "subject:create",
            "subject:read",
            "subject:update",
            "subject:list",
            "document:create",
            "document:read",
            "event_schema:read",
        ],
        "is_system": True,
    },
    "auditor": {
        "name": "Auditor (Read-Only)",
        "description": "Read-only access to events and subjects",
        "permissions": [
            "event:read",
            "event:list",
            "subject:read",
            "subject:list",
            "document:read",
            "event_schema:read",
        ],
        "is_system": True,
    },
}

class InitializationResult(TypedDict):  
    """Result of tenant initialization"""  
    permissions_created: int  
    roles_created: int  
    admin_role_assigned: bool  

    
class TenantInitializationService:
    """Service for initializing new tenants with default RBAC setup"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def initialize_tenant(self, tenant_id: str, admin_user_id: str) -> InitializationResult:
        """
        Initialize a new tenant with:
        - Default permissions
        - Default roles
        - Admin role assigned to the admin user

        Returns a dict with created entities count
        """
        # Create permissions
        permission_map = await self._create_permissions(tenant_id)

        # Create roles with permission assignments
        roles = await self._create_roles(tenant_id, permission_map)

        # Assign admin role to admin user
        await self._assign_admin_role(tenant_id, admin_user_id, roles["admin"])

        return {
            "permissions_created": len(permission_map),
            "roles_created": len(roles),
            "admin_role_assigned": True,
        }

    async def _create_permissions(self, tenant_id: str) -> dict[str, str]:
        """Create default permissions for a tenant. Returns mapping of code -> permission_id"""
        permission_map: dict[str, str] = {}
        permissions: list[Permission] = []

        for code, resource, action, description in SYSTEM_PERMISSIONS:
            perm_id = generate_cuid()
            permission = Permission(
                id=perm_id,
                tenant_id=tenant_id,
                code=code,
                resource=resource,
                action=action,
                description=description,
            )
            permissions.append(permission)
            permission_map[code] = perm_id

        self.db.add_all(permissions)
        await self.db.flush()
        return permission_map

    async def _create_roles(
        self, tenant_id: str, permission_map: dict[str, str]
    ) -> dict[str, str]:
        """Create default roles with permissions. Returns mapping of role_code -> role_id"""
        role_map: dict[str, str] = {}
        roles: list[Role] = []
        role_permissions: list[RolePermission] = []

        for role_code, role_data in DEFAULT_ROLES.items():
            # Pre-generate role ID
            role_id = generate_cuid()

            # Create role
            role = Role(
                id=role_id,
                tenant_id=tenant_id,
                code=role_code,
                name=role_data["name"],
                description=role_data["description"],
                is_system=role_data["is_system"],
                is_active=True,
            )
            roles.append(role)
            role_map[role_code] = role_id

            # Assign permissions to role
            for perm_pattern in role_data["permissions"]:
                # Handle wildcards (e.g., "event:*" means all event permissions)
                matching_perms: list[tuple[str, str]] = []
                if perm_pattern.endswith(":*"):
                    resource_prefix = perm_pattern[:-2]
                    matching_perms = [
                        (code, perm_id)
                        for code, perm_id in permission_map.items()
                        if code.startswith(resource_prefix + ":")
                    ]
                else:
                    perm_id = permission_map.get(perm_pattern)
                    if perm_id:
                        matching_perms = [(perm_pattern, perm_id)]

                for _, perm_id in matching_perms:
                    role_permission = RolePermission(
                        id=generate_cuid(),
                        tenant_id=tenant_id,
                        role_id=role_id,
                        permission_id=perm_id,
                    )
                    role_permissions.append(role_permission)

        # Batch insert all roles and role-permissions
        self.db.add_all(roles)
        self.db.add_all(role_permissions)
        await self.db.flush()

        return role_map

    async def _assign_admin_role(
        self, tenant_id: str, user_id: str, admin_role_id: str
    ) -> None:
        """Assign admin role to the specified user"""
        user_role = UserRole(
            id=generate_cuid(),
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=admin_role_id,
            assigned_by=user_id,  # Self-assigned for the first admin
        )
        self.db.add(user_role)
        await self.db.flush()
