"""
Domain layer - Enterprise Business Rules.

This is the innermost layer containing business entities, value objects,
and domain exceptions. It has no dependencies on other layers.
"""

from src.domain.entities import EventEntity, TenantEntity
from src.domain.enums import TenantStatus
from src.domain.exceptions import (AuthenticationException,
                                   AuthorizationException,
                                   EventChainBrokenException,
                                   PermissionDeniedError,
                                   ResourceNotFoundException,
                                   SchemaValidationException,
                                   TenantNotFoundException, TimelineException,
                                   ValidationException)
from src.domain.value_objects import (EventChain, EventType, Hash, SubjectId,
                                      TenantCode, TenantId)

__all__ = [
    # Entities
    "EventEntity",
    "TenantEntity",
    # Value Objects
    "TenantCode",
    "TenantId",
    "SubjectId",
    "EventType",
    "Hash",
    "EventChain",
    # Enums
    "TenantStatus",
    # Exceptions
    "TimelineException",
    "ValidationException",
    "AuthenticationException",
    "AuthorizationException",
    "TenantNotFoundException",
    "ResourceNotFoundException",
    "EventChainBrokenException",
    "SchemaValidationException",
    "PermissionDeniedError",
]
