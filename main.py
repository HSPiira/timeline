import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession

from api import (
    auth,
    documents,
    email_accounts,
    event_schemas,
    events,
    oauth_providers,
    permissions,
    roles,
    subjects,
    tenants,
    user_roles,
    users,
    workflows,
)
from api.deps import get_cache_service, set_cache_service
from core.config import get_settings
from core.database import engine, get_db
from core.logging import setup_logging
from core.rate_limit import limiter
from core.telemetry import TelemetryConfig, get_telemetry, set_telemetry
from middleware.correlation import CorrelationIDMiddleware
from middleware.security import RequestSizeLimitMiddleware, SecurityHeadersMiddleware
from services.cache_service import CacheService

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for application initialization and cleanup"""
    # Initialize logging
    setup_logging()

    # Database schema is managed by Alembic migrations
    # Run migrations: alembic upgrade head

    # Initialize OpenTelemetry distributed tracing
    if settings.telemetry_enabled:
        try:
            telemetry = TelemetryConfig(
                service_name=settings.app_name,
                service_version=settings.app_version,
                enabled=True,
            )

            # Setup telemetry with configured exporter
            telemetry.setup_telemetry(
                exporter_type=settings.telemetry_exporter,
                otlp_endpoint=settings.telemetry_otlp_endpoint,
                jaeger_endpoint=settings.telemetry_jaeger_endpoint,
                sample_rate=settings.telemetry_sample_rate,
            )

            # Instrument FastAPI
            telemetry.instrument_fastapi(app)

            # Instrument SQLAlchemy
            telemetry.instrument_sqlalchemy(engine)

            # Instrument Redis (if enabled)
            if settings.redis_enabled:
                telemetry.instrument_redis()

            # Instrument logging for trace correlation
            telemetry.instrument_logging()

            set_telemetry(telemetry)
            logger.info(
                f"Distributed tracing initialized: exporter={settings.telemetry_exporter}"
            )
        except Exception as e:
            logger.warning(
                f"Telemetry initialization failed: {e}. Continuing without tracing."
            )
    else:
        logger.info("Distributed tracing disabled in configuration")

    # Initialize Redis cache
    if settings.redis_enabled:
        try:
            cache_service = CacheService()
            await cache_service.connect()
            set_cache_service(cache_service)
            logger.info("Redis cache initialized successfully")
        except Exception as e:
            logger.warning(
                f"Redis cache initialization failed: {e}. Continuing without cache."
            )
    else:
        logger.info("Redis cache disabled in configuration")

    yield

    # Shutdown: close connections
    # Shutdown telemetry (flush remaining spans)
    if settings.telemetry_enabled:
        try:
            telemetry_instance = get_telemetry()
            if telemetry_instance:
                telemetry_instance.shutdown()
        except Exception as e:
            logger.warning(f"Error during telemetry shutdown: {e}")

    # Shutdown cache
    if settings.redis_enabled:
        try:
            cache = await get_cache_service()
            await cache.disconnect()
            logger.info("Redis cache disconnected")
        except Exception as e:
            logger.warning(f"Error during cache shutdown: {e}")

    await engine.dispose()
    logger.info("Database engine disposed")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security middleware (order matters - applied in reverse)
# 1. Request size limit (first check)
app.add_middleware(
    RequestSizeLimitMiddleware, max_request_size=10 * 1024 * 1024
)  # 10MB

# 2. Correlation ID for request tracing
app.add_middleware(CorrelationIDMiddleware)

# 3. Security headers
app.add_middleware(SecurityHeadersMiddleware)

# 4. CORS middleware
# Security: Using allow_credentials=True requires specific origins (not wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(oauth_providers.router, prefix="/api", tags=["oauth"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
app.include_router(subjects.router, prefix="/subjects", tags=["subjects"])
app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(
    event_schemas.router, prefix="/event-schemas", tags=["event-schemas"]
)
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(roles.router, prefix="/roles", tags=["roles"])
app.include_router(permissions.router, prefix="/permissions", tags=["permissions"])
app.include_router(user_roles.router, prefix="", tags=["user-roles"])
app.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
app.include_router(
    email_accounts.router, prefix="/email-accounts", tags=["email-accounts"]
)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint for load balancers and monitoring.

    Validates:
    - API is responsive
    - Database connectivity
    - Redis cache availability (optional)

    Returns:
    - 200 OK if healthy
    - 503 Service Unavailable if unhealthy
    """
    from typing import Any

    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    checks: dict[str, Any] = {
        "api": True,  # If we got here, API is responding
        "database": False,
        "cache": None,  # None = not configured, True = healthy, False = unhealthy
    }

    try:
        # Check database connectivity
        await db.execute(text("SELECT 1"))
        checks["database"] = True

        # Check Redis cache (optional - won't fail health check if disabled)
        if settings.redis_enabled:
            cache = await get_cache_service()
            checks["cache"] = cache.is_available()

        # Overall health check - cache is optional, database and API are required
        is_healthy = checks["api"] and checks["database"]

        if is_healthy:
            return {"status": "healthy", "checks": checks}
        else:
            return JSONResponse(
                status_code=503, content={"status": "unhealthy", "checks": checks}
            )
    except Exception as e:
        checks["error"] = str(e)
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "checks": checks}
        )
