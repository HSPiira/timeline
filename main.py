from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.database import engine
from api import auth, events, subjects, tenants, documents, users, event_schemas, roles, permissions, user_roles

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for database initialization"""
    # Database schema is managed by Alembic migrations
    # Run migrations: alembic upgrade head

    yield

    # Shutdown: dispose engine
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan
)

# CORS middleware
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
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
app.include_router(subjects.router, prefix="/subjects", tags=["subjects"])
app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(event_schemas.router, prefix="/event-schemas", tags=["event-schemas"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(roles.router, prefix="/roles", tags=["roles"])
app.include_router(permissions.router, prefix="/permissions", tags=["permissions"])
app.include_router(user_roles.router, prefix="", tags=["user-roles"])


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}