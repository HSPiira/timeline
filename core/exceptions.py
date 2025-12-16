from fastapi import HTTPException, status

class TimelineException(Exception):
    """Base exception"""
    pass

class TenantNotFoundException(TimelineException):
    """Tenant not found"""
    pass

class EventChainBrokenException(TimelineException):
    """Event chain integrity violated"""
    pass

class SchemaValidationException(TimelineException):
    """Schema validation failed"""
    pass

class PermissionDeniedError(TimelineException):
    """Permission denied - user lacks required permission"""
    pass