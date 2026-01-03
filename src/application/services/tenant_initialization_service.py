"""
Tenant initialization service for setting up RBAC and default data.

This service is called when a new tenant is created to set up:
- Default permissions
- Default roles (admin, manager, agent, auditor)
- Role-permission assignments
- System audit schema and subject for audit trail
"""
from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.system_audit_schema import (
    SYSTEM_AUDIT_EVENT_TYPE,
    SYSTEM_AUDIT_SCHEMA_VERSION,
    SYSTEM_AUDIT_SUBJECT_REF,
    SYSTEM_AUDIT_SUBJECT_TYPE,
    get_system_audit_schema_definition,
)
from src.infrastructure.persistence.models.event_schema import EventSchema
from src.infrastructure.persistence.models.permission import Permission, RolePermission, UserRole
from src.infrastructure.persistence.models.role import Role
from src.infrastructure.persistence.models.subject import Subject
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
    audit_schema_created: bool
    audit_subject_created: bool


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
        - System audit schema for tracking all CRUD operations
        - System audit subject for audit event chain

        Uses a single flush at the end for optimal database performance.
        Returns a dict with created entities count.
        """
        # Collect all entities to insert
        permissions, permission_map = self._build_permissions(tenant_id)
        roles, role_permissions, role_map = self._build_roles(tenant_id, permission_map)
        user_role = self._build_admin_assignment(tenant_id, admin_user_id, role_map["admin"])

        # Build system audit infrastructure
        audit_schema = self._build_audit_schema(tenant_id, admin_user_id)
        audit_subject = self._build_audit_subject(tenant_id)

        # Batch insert all entities with single flush
        self.db.add_all(permissions)
        self.db.add_all(roles)
        self.db.add_all(role_permissions)
        self.db.add(user_role)
        self.db.add(audit_schema)
        self.db.add(audit_subject)
        await self.db.flush()

        return {
            "permissions_created": len(permission_map),
            "roles_created": len(role_map),
            "admin_role_assigned": True,
            "audit_schema_created": True,
            "audit_subject_created": True,
        }

    def _build_permissions(self, tenant_id: str) -> tuple[list[Permission], dict[str, str]]:
        """Build permission entities. Returns (permissions list, code->id map)"""
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

        return permissions, permission_map

    def _build_roles(
        self, tenant_id: str, permission_map: dict[str, str]
    ) -> tuple[list[Role], list[RolePermission], dict[str, str]]:
        """Build role and role-permission entities."""
        role_map: dict[str, str] = {}
        roles: list[Role] = []
        role_permissions: list[RolePermission] = []

        for role_code, role_data in DEFAULT_ROLES.items():
            role_id = generate_cuid()

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
                matching_perms = self._resolve_permission_pattern(perm_pattern, permission_map)
                for perm_id in matching_perms:
                    role_permission = RolePermission(
                        id=generate_cuid(),
                        tenant_id=tenant_id,
                        role_id=role_id,
                        permission_id=perm_id,
                    )
                    role_permissions.append(role_permission)

        return roles, role_permissions, role_map

    @staticmethod
    def _resolve_permission_pattern(
        pattern: str, permission_map: dict[str, str]
    ) -> list[str]:
        """Resolve permission pattern (e.g., 'event:*') to list of permission IDs"""
        if pattern.endswith(":*"):
            resource_prefix = pattern[:-2]
            return [
                perm_id
                for code, perm_id in permission_map.items()
                if code.startswith(resource_prefix + ":")
            ]
        perm_id = permission_map.get(pattern)
        return [perm_id] if perm_id else []

    @staticmethod
    def _build_admin_assignment(tenant_id: str, user_id: str, admin_role_id: str) -> UserRole:
        """Build admin role assignment entity"""
        return UserRole(
            id=generate_cuid(),
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=admin_role_id,
            assigned_by=user_id,  # Self-assigned for the first admin
        )

    @staticmethod
    def _build_audit_schema(tenant_id: str, created_by: str) -> EventSchema:
        """
        Build the system audit EventSchema for tracking all CRUD operations.

        This schema is:
        - Created once per tenant during initialization
        - Activated immediately (is_active=True)
        - Used by SystemAuditService for all audit events
        """
        return EventSchema(
            id=generate_cuid(),
            tenant_id=tenant_id,
            event_type=SYSTEM_AUDIT_EVENT_TYPE,
            schema_definition=get_system_audit_schema_definition(),
            version=SYSTEM_AUDIT_SCHEMA_VERSION,
            is_active=True,  # Auto-activate system schema
            created_by=created_by,
        )

    @staticmethod
    def _build_audit_subject(tenant_id: str) -> Subject:
        """
        Build the system audit Subject for the audit event chain.

        This subject:
        - Acts as the "subject" for all audit events in this tenant
        - Has a reserved external_ref to identify it uniquely
        - Enables hash chaining across all audit events
        """
        return Subject(
            id=generate_cuid(),
            tenant_id=tenant_id,
            subject_type=SYSTEM_AUDIT_SUBJECT_TYPE,
            external_ref=SYSTEM_AUDIT_SUBJECT_REF,
        )
