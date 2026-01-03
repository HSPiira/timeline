"""
Domain exceptions for the Timeline application.

This module defines domain-level exceptions that represent business rule violations.
These exceptions are independent of infrastructure concerns.
"""

from typing import Any


class TimelineException(Exception):
    """
    Base exception for all Timeline application errors.

    All custom exceptions should inherit from this class to allow
    for consistent error handling and logging.

    Attributes:
        message: Human-readable error description
        error_code: Machine-readable error code for API responses
        details: Additional error context
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class ValidationException(TimelineException):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str | None = None):
        details = {"field": field} if field else {}
        super().__init__(message, "VALIDATION_ERROR", details)


class AuthenticationException(TimelineException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTHENTICATION_ERROR")


class AuthorizationException(TimelineException):
    """Raised when user lacks required permissions."""

    def __init__(self, resource: str, action: str):
        message = f"Permission denied: {action} on {resource}"
        super().__init__(message, "AUTHORIZATION_ERROR", {"resource": resource, "action": action})


class TenantNotFoundException(TimelineException):
    """Raised when tenant is not found."""

    def __init__(self, tenant_id: str):
        super().__init__(
            f"Tenant not found: {tenant_id}",
            "TENANT_NOT_FOUND",
            {"tenant_id": tenant_id},
        )


class ResourceNotFoundException(TimelineException):
    """Raised when a requested resource is not found."""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            f"{resource_type} not found: {resource_id}",
            "RESOURCE_NOT_FOUND",
            {"resource_type": resource_type, "resource_id": resource_id},
        )


class EventChainBrokenException(TimelineException):
    """Raised when event chain integrity is violated."""

    def __init__(self, subject_id: str, event_id: str, reason: str):
        super().__init__(
            f"Event chain broken for subject {subject_id}",
            "CHAIN_INTEGRITY_ERROR",
            {"subject_id": subject_id, "event_id": event_id, "reason": reason},
        )


class SchemaValidationException(TimelineException):
    """Raised when schema validation fails."""

    def __init__(self, schema_type: str, validation_errors: list[Any]):
        super().__init__(
            f"Schema validation failed for {schema_type}",
            "SCHEMA_VALIDATION_ERROR",
            {"schema_type": schema_type, "errors": validation_errors},
        )


class PermissionDeniedError(TimelineException):
    """Permission denied - user lacks required permission."""

    def __init__(
        self,
        message: str = "Permission denied",
        resource: str | None = None,
        action: str | None = None,
    ):
        details: dict[str, Any] = {}
        if resource:
            details["resource"] = resource
        if action:
            details["action"] = action
        super().__init__(message, "PERMISSION_DENIED", details)
