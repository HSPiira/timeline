from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import verify_token
from core.database import get_db, get_db_transactional
from models.tenant import Tenant
from repositories.document_repo import DocumentRepository
from repositories.event_repo import EventRepository
from repositories.event_schema_repo import EventSchemaRepository
from repositories.subject_repo import SubjectRepository
from repositories.tenant_repo import TenantRepository
from repositories.user_repo import UserRepository
from schemas.token import TokenPayload
from services.authz_service import AuthorizationService
from services.cache_service import CacheService
from services.document_service import DocumentService
from services.event_service import EventService
from services.hash_service import HashService

security = HTTPBearer()

# Global service instances (singletons)
_storage_service = None
_cache_service: CacheService | None = None


# Cache service dependencies (defined early for use in other dependencies)
async def get_cache_service() -> CacheService:
    """
    Cache service dependency (singleton)

    Returns global cache service instance.
    Initialized on app startup in main.py
    """
    global _cache_service
    if _cache_service is None:
        # Initialize cache service if not already done
        _cache_service = CacheService()
        # Note: connect() should be called on app startup in main.py
    return _cache_service


def set_cache_service(cache_service: CacheService):
    """Set global cache service (called on app startup)"""
    global _cache_service
    _cache_service = cache_service


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """
    Validate JWT token and return authenticated user payload.
    Token must contain 'sub' (user_id) and 'tenant_id' claims.
    """
    try:
        payload = verify_token(credentials.credentials)
        token_data = TokenPayload(**payload)
        return token_data
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_tenant(
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> Tenant:
    """
    Get current tenant from authenticated user's token claims.
    Tenant ID is derived from JWT token, preventing header spoofing attacks.
    Uses Redis cache for performance optimization.
    """
    tenant = await TenantRepository(db, cache_service=cache).get_by_id(user.tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant not found or access denied",
        )
    return tenant


def _build_event_service(
    db: AsyncSession, cache_service: CacheService | None = None
) -> EventService:
    """Internal helper to construct EventService with all dependencies"""
    from services.workflow_engine import WorkflowEngine

    event_repo = EventRepository(db)
    event_service = EventService(
        event_repo=event_repo,
        hash_service=HashService(),
        subject_repo=SubjectRepository(db),
        schema_repo=EventSchemaRepository(db, cache_service=cache_service),
    )

    # Add workflow engine
    workflow_engine = WorkflowEngine(db, event_service)
    event_service.workflow_engine = workflow_engine

    return event_service


async def get_event_service(
    db: AsyncSession = Depends(get_db), cache: CacheService = Depends(get_cache_service)
) -> EventService:
    """Event service dependency with caching"""
    return _build_event_service(db, cache)


async def get_subject_repo(db: AsyncSession = Depends(get_db)) -> SubjectRepository:
    """Subject repository dependency"""
    return SubjectRepository(db)


async def get_event_repo(db: AsyncSession = Depends(get_db)) -> EventRepository:
    """Event repository dependency"""
    return EventRepository(db)


async def get_tenant_repo(
    db: AsyncSession = Depends(get_db), cache: CacheService = Depends(get_cache_service)
) -> TenantRepository:
    """Tenant repository dependency with caching"""
    return TenantRepository(db, cache_service=cache)


async def get_document_repo(db: AsyncSession = Depends(get_db)) -> DocumentRepository:
    """Document repository dependency"""
    return DocumentRepository(db)


async def get_user_repo(db: AsyncSession = Depends(get_db)) -> UserRepository:
    """User repository dependency"""
    return UserRepository(db)


async def get_event_schema_repo(
    db: AsyncSession = Depends(get_db), cache: CacheService = Depends(get_cache_service)
) -> EventSchemaRepository:
    """Event schema repository dependency with caching"""
    return EventSchemaRepository(db, cache_service=cache)


# Transactional dependencies for write operations
async def get_event_service_transactional(
    db: AsyncSession = Depends(get_db_transactional),
    cache: CacheService = Depends(get_cache_service),
) -> EventService:
    """Event service dependency with transaction management and caching"""
    return _build_event_service(db, cache)


async def get_subject_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional),
) -> SubjectRepository:
    """Subject repository dependency with transaction management"""
    return SubjectRepository(db)


async def get_tenant_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional),
    cache: CacheService = Depends(get_cache_service),
) -> TenantRepository:
    """Tenant repository dependency with transaction management and caching"""
    return TenantRepository(db, cache_service=cache)


async def get_document_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional),
) -> DocumentRepository:
    """Document repository dependency with transaction management"""
    return DocumentRepository(db)


async def get_user_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional),
) -> UserRepository:
    """User repository dependency with transaction management"""
    return UserRepository(db)


async def get_event_schema_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional),
    cache: CacheService = Depends(get_cache_service),
) -> EventSchemaRepository:
    """Event schema repository dependency with transaction management and caching"""
    return EventSchemaRepository(db, cache_service=cache)


# Storage service dependencies
async def get_storage_service():
    """Storage service dependency"""
    global _storage_service
    if _storage_service is not None:
        return _storage_service

    from core.config import get_settings
    from services.storage.factory import StorageFactory

    settings = get_settings()
    _storage_service = StorageFactory.create_storage_service(settings)
    return _storage_service


async def get_document_service(
    storage=Depends(get_storage_service),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> "DocumentService":
    """Document service dependency with caching"""
    from services.document_service import DocumentService

    return DocumentService(
        storage_service=storage,
        document_repo=DocumentRepository(db),
        tenant_repo=TenantRepository(db, cache_service=cache),
    )


async def get_document_service_transactional(
    storage=Depends(get_storage_service),
    db: AsyncSession = Depends(get_db_transactional),
    cache: CacheService = Depends(get_cache_service),
) -> "DocumentService":
    """Document service dependency with transaction and caching"""
    from services.document_service import DocumentService

    return DocumentService(
        storage_service=storage,
        document_repo=DocumentRepository(db),
        tenant_repo=TenantRepository(db, cache_service=cache),
    )


def require_permission(resource: str, action: str):
    """
    Dependency factory for route-level permission checking.

    Usage:
        @router.post("/events/", dependencies=[Depends(require_permission("event", "create"))])
        async def create_event(...):
            ...
    """

    async def permission_checker(
        user: TokenPayload = Depends(get_current_user),
        authz_service: AuthorizationService = Depends(get_authz_service),
    ) -> TokenPayload:
        has_permission = await authz_service.check_permission(
            user_id=user.sub, tenant_id=user.tenant_id, resource=resource, action=action
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}:{action} required",
            )

        return user

    return permission_checker


# Alternative: Inject authorization service for complex checks
async def get_authz_service(
    db: AsyncSession = Depends(get_db), cache: CacheService = Depends(get_cache_service)
) -> AuthorizationService:
    """Get authorization service for manual permission checks with caching"""
    return AuthorizationService(db, cache_service=cache)
