"""
Tenant domain entity.

This represents the business concept of a tenant, independent of
how it's stored in the database.
"""

from dataclasses import dataclass
from datetime import datetime

from src.domain.enums import TenantStatus
from src.domain.value_objects.core import TenantId


@dataclass
class TenantEntity:
    """
    Domain entity for Tenant (SRP - business logic separate from persistence)
    """

    id: TenantId
    code: str
    name: str
    status: TenantStatus
    created_at: datetime

    def can_create_events(self) -> bool:
        """Business rule: only active tenants can create events"""
        return self.status == TenantStatus.ACTIVE

    def activate(self) -> None:
        """Activate tenant"""
        self.status = TenantStatus.ACTIVE

    def suspend(self) -> None:
        """Suspend tenant"""
        self.status = TenantStatus.SUSPENDED

    def archive(self) -> None:
        """Archive tenant"""
        self.status = TenantStatus.ARCHIVED
