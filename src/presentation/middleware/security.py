"""Security middleware for HTTP security headers and request validation"""
import logging
import uuid
from collections.abc import Callable

from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.infrastructure.config.settings import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add comprehensive security headers to all HTTP responses.

    Headers added:
    - X-Frame-Options: Prevents clickjacking attacks
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-XSS-Protection: Enables browser XSS filter
    - Strict-Transport-Security: Forces HTTPS (production only)
    - Content-Security-Policy: Restricts resource loading
    - Referrer-Policy: Controls referrer information
    - Permissions-Policy: Controls browser features
    - X-Permitted-Cross-Domain-Policies: Controls cross-domain policies
    - Expect-CT: Certificate Transparency
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            raise

        # Core security headers
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Enhanced Permissions Policy
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # Additional security headers
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # Certificate Transparency
        if request.url.scheme == "https":
            response.headers["Expect-CT"] = "max-age=86400, enforce"

        # Force HTTPS in production with enhanced HSTS
        if request.url.scheme == "https" or (
            hasattr(settings, "environment") and settings.environment == "production"
        ):
            response.headers[
                "Strict-Transport-Security"
            ] = "max-age=63072000; includeSubDomains; preload"  # 2 years

        # Content Security Policy
        # Relax CSP for API documentation endpoints
        if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            # Permissive CSP for Swagger UI and ReDoc
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://cdn.jsdelivr.net; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "base-uri 'self';"
            )
        else:
            # Strict CSP for API endpoints
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "media-src 'none'; "
                "object-src 'none'; "
                "frame-src 'none'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "base-uri 'self';"
            )

        # Remove server header if present (information disclosure)
        if "server" in response.headers:
            del response.headers["server"]

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Limit request body size to prevent DoS attacks.

    Default limit: 10MB
    Can be overridden per-endpoint using Body(..., max_size=...)
    """

    def __init__(self, app, max_request_size: int = 10 * 1024 * 1024) -> None:
        """
        Initialize middleware with max request size.

        Args:
            app: FastAPI application
            max_request_size: Maximum allowed request size in bytes (default 10MB)
        """
        super().__init__(app)
        self.max_request_size = max_request_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check request size before processing."""
        # Check Content-Length header
        content_length = request.headers.get("content-length")

        if content_length:
            try:
                content_length_int = int(content_length)
                if content_length_int > self.max_request_size:
                    logger.warning(
                        f"Request size {content_length_int} exceeds limit {self.max_request_size} "
                        f"from {request.client.host if request.client else 'unknown'}"
                    )
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "PAYLOAD_TOO_LARGE",
                            "message": f"Request body too large. Maximum size: {self.max_request_size} bytes",
                            "details": {
                                "max_size_bytes": self.max_request_size,
                                "received_size_bytes": content_length_int,
                            },
                        },
                    )
            except ValueError:
                logger.error(f"Invalid Content-Length header: {content_length}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "INVALID_CONTENT_LENGTH",
                        "message": "Invalid Content-Length header",
                    },
                )

        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Add request ID for tracing and debugging.

    Adds a unique request ID to each request for correlation
    across logs and responses.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add request ID to request and response."""
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in request state for access in handlers
        request.state.request_id = request_id

        # Log request with ID
        logger.info(
            f"Request {request_id}: {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )

        # Process request
        response = await call_next(request)

        # Add request ID to response
        response.headers["X-Request-ID"] = request_id

        # Log response
        logger.info(f"Response {request_id}: status={response.status_code}")

        return response
