"""Correlation ID middleware for request tracing"""
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Context variable to store correlation ID for the current request
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Add correlation IDs to all requests for distributed tracing.

    Features:
    - Generates unique correlation ID for each request
    - Accepts X-Correlation-ID header from clients
    - Adds correlation ID to response headers
    - Makes correlation ID available to logging system

    Usage in logs:
        from middleware.correlation import get_correlation_id
        logger.info(f"[{get_correlation_id()}] Processing request")
    """

    async def dispatch(self, request: Request, call_next):
        # Get correlation ID from header or generate new one
        correlation_id = request.headers.get("X-Correlation-ID")

        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in context variable (accessible throughout request lifecycle)
        correlation_id_var.set(correlation_id)

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response


def get_correlation_id() -> str:
    """Get the correlation ID for the current request"""
    return correlation_id_var.get()
