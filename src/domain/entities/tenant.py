"""
Tenant domain entity.

This represents the business concept of a tenant, independent of
how it's stored in the database.
"""

from dataclasses import dataclass

from src.domain.enums import TenantStatus
from src.domain.value_objects.core import TenantCode


@dataclass
class TenantEntity:
    """
    Domain entity for Tenant (SRP - business logic separate from persistence)
    """

    id: str
    code: TenantCode
    name: str
    status: TenantStatus

    def can_create_events(self) -> bool:
        """
        Business rule: only ACTIVE tenants can create events
        """
        return self.status == TenantStatus.ACTIVE

    def activate(self) -> None:
        """
        Activate tenant.
        Only active tenants can create events.
        Archived tenants cannot be activated.
        Suspended tenants can be activated.
        """
        if self.status == TenantStatus.ARCHIVED:
            raise ValueError("Archived tenants cannot be activated")
        self.status = TenantStatus.ACTIVE

    def suspend(self) -> None:
        """
        Suspend tenant.
        Suspended tenants cannot create events.
        Archived tenants cannot be suspended.
        """
        if self.status == TenantStatus.ARCHIVED:
            raise ValueError("Archived tenants cannot be suspended")
        self.status = TenantStatus.SUSPENDED

    def archive(self) -> None:
        """
        Archive tenant.
        Archiving is irreversible.
        """
        if self.status == TenantStatus.ARCHIVED:
            raise ValueError("Tenant is already archived")
        self.status = TenantStatus.ARCHIVED

    def change_code(self, new_code: TenantCode) -> None:
        """
        Change tenant code.
        Tenant codes are immutable once the tenant is ACTIVE.
        """
        if self.status == TenantStatus.ACTIVE:
            raise ValueError("Tenant code cannot be changed once tenant is active")
        self.code = new_code
