"""
Seed default RBAC permissions and roles for all tenants.

Usage:
    python -m scripts.seed_rbac
"""
import asyncio
from typing import TypedDict

from sqlalchemy import select

from core.database import AsyncSessionLocal
from models.permission import Permission, RolePermission
from models.role import Role
from models.tenant import Tenant
from utils.generators import generate_cuid


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


async def seed_permissions_for_tenant(db, tenant_id: str) -> dict[str, str]:
    """Create default permissions for a tenant. Returns mapping of code -> permission_id"""
    permission_map = {}

    for code, resource, action, description in SYSTEM_PERMISSIONS:
        # Check if permission already exists
        result = await db.execute(
            select(Permission).where(
                Permission.tenant_id == tenant_id, Permission.code == code
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            permission_map[code] = existing.id
            continue

        # Create permission
        permission = Permission(
            id=generate_cuid(),
            tenant_id=tenant_id,
            code=code,
            resource=resource,
            action=action,
            description=description,
        )
        db.add(permission)
        await db.flush()
        permission_map[code] = permission.id
        print(f"  ✓ Created permission: {code}")

    return permission_map


async def seed_roles_for_tenant(db, tenant_id: str, permission_map: dict[str, str]):
    """Create default roles with permissions for a tenant"""

    for role_code, role_data in DEFAULT_ROLES.items():
        # Check if role already exists
        result = await db.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.code == role_code)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"  ℹ Role already exists: {role_code}")
            continue

        # Create role
        role = Role(
            id=generate_cuid(),
            tenant_id=tenant_id,
            code=role_code,
            name=role_data["name"],
            description=role_data["description"],
            is_system=role_data["is_system"],
            is_active=True,
        )
        db.add(role)
        await db.flush()
        print(f"  ✓ Created role: {role_code} ({role_data['name']})")

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

            for perm_code, perm_id in matching_perms:
                if not perm_id:
                    print(f"    ⚠ Permission not found: {perm_code}")
                    continue

                role_permission = RolePermission(
                    id=generate_cuid(),
                    tenant_id=tenant_id,
                    role_id=role.id,
                    permission_id=perm_id,
                )
                db.add(role_permission)

        await db.flush()
        print(f"    ✓ Assigned {len(role_data['permissions'])} permission(s)")


async def seed_all_tenants():
    """Seed RBAC data for all active tenants"""
    async with AsyncSessionLocal() as db:
        # Get all active tenants
        result = await db.execute(select(Tenant).where(Tenant.status == "active"))
        tenants = result.scalars().all()

        print(f"\n🌱 Seeding RBAC data for {len(tenants)} tenant(s)...\n")

        for tenant in tenants:
            print(f"📦 Tenant: {tenant.name} ({tenant.code})")

            # Seed permissions
            permission_map = await seed_permissions_for_tenant(db, tenant.id)
            print(f"  ✓ Seeded {len(permission_map)} permissions")

            # Seed roles
            await seed_roles_for_tenant(db, tenant.id, permission_map)

            # Commit changes for this tenant
            await db.commit()
            print(f"  ✅ Completed for tenant: {tenant.code}\n")

        print("✅ RBAC seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed_all_tenants())
