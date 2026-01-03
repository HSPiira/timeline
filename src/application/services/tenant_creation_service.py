"""
Tenant creation service for orchestrating new tenant setup.

This service encapsulates the complete tenant creation workflow:
- Tenant record creation
- Admin user creation with secure password
- RBAC initialization (permissions, roles, assignments)

Follows clean architecture by keeping business logic in the application layer.
"""

import secrets
import string
from dataclasses import dataclass

from src.domain.enums import TenantStatus
from src.infrastructure.persistence.models.tenant import Tenant
from src.infrastructure.persistence.repositories.tenant_repo import TenantRepository
from src.infrastructure.persistence.repositories.user_repo import UserRepository

from .tenant_initialization_service import TenantInitializationService


@dataclass
class TenantCreationResult:
    """Result of tenant creation operation"""

    tenant: Tenant
    admin_username: str
    admin_password: str


class TenantCreationService:
    """
    Service for creating new tenants with complete RBAC setup.

    Orchestrates:
    1. Tenant record creation
    2. Admin user creation with cryptographically secure password
    3. RBAC initialization via TenantInitializationService
    """

    def __init__(
        self,
        tenant_repo: TenantRepository,
        user_repo: UserRepository,
        init_service: TenantInitializationService,
    ) -> None:
        self.tenant_repo = tenant_repo
        self.user_repo = user_repo
        self.init_service = init_service

    async def create_tenant(
        self,
        code: str,
        name: str,
        admin_password: str | None = None,
    ) -> TenantCreationResult:
        """
        Create a new tenant with admin user and RBAC setup.

        Args:
            code: Unique tenant code (used in URLs, admin email)
            name: Display name for the tenant
            admin_password: Optional password for admin user (generated if not provided)

        Returns:
            TenantCreationResult with tenant, admin credentials

        Raises:
            IntegrityError: If tenant code already exists
        """
        # Create tenant entity
        tenant = Tenant(
            code=code,
            name=name,
            status=TenantStatus.ACTIVE.value,
        )
        created_tenant = await self.tenant_repo.create(tenant)

        # Initialize RBAC first (creates audit subject needed for user audit events)
        # Note: We pass a placeholder user_id since admin user doesn't exist yet.
        # The admin role assignment is handled separately after user creation.
        await self.init_service.initialize_tenant_infrastructure(
            tenant_id=created_tenant.id,
        )

        # Generate secure password if not provided
        password = admin_password or self._generate_secure_password()

        # Create admin user (now audit subject exists for audit events)
        admin_username = "admin"
        admin_email = f"admin@{code}.tl"
        admin_user = await self.user_repo.create_user(
            tenant_id=created_tenant.id,
            username=admin_username,
            email=admin_email,
            password=password,
        )

        # Complete initialization by assigning admin role
        await self.init_service.assign_admin_role(
            tenant_id=created_tenant.id,
            admin_user_id=admin_user.id,
        )

        return TenantCreationResult(
            tenant=created_tenant,
            admin_username=admin_username,
            admin_password=password,
        )

    @staticmethod
    def _generate_secure_password(length: int = 16) -> str:
        """
        Generate a cryptographically secure random password.

        Uses secrets module for cryptographic randomness.
        Password contains uppercase, lowercase, digits, and special characters.
        """
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
        return "".join(secrets.choice(alphabet) for _ in range(length))
