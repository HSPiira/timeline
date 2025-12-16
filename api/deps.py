from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, get_db_transactional
from core.auth import verify_token
from models.tenant import Tenant
from repositories.tenant_repo import TenantRepository
from repositories.event_repo import EventRepository
from repositories.subject_repo import SubjectRepository
from repositories.document_repo import DocumentRepository
from repositories.user_repo import UserRepository
from repositories.event_schema_repo import EventSchemaRepository
from services.authz_service import AuthorizationService
from services.event_service import EventService
from services.hash_service import HashService
from schemas.token import TokenPayload

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
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
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_tenant(
    user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """
    Get current tenant from authenticated user's token claims.
    Tenant ID is derived from JWT token, preventing header spoofing attacks.
    """
    tenant = await TenantRepository(db).get_by_id(user.tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant not found or access denied"
        )
    return tenant


async def get_event_service(
    db: AsyncSession = Depends(get_db)
) -> EventService:
    """Event service dependency"""
    return EventService(
        event_repo=EventRepository(db),
        hash_service=HashService(),
        schema_repo=EventSchemaRepository(db)
    )


async def get_subject_repo(
    db: AsyncSession = Depends(get_db)
) -> SubjectRepository:
    """Subject repository dependency"""
    return SubjectRepository(db)


async def get_event_repo(
    db: AsyncSession = Depends(get_db)
) -> EventRepository:
    """Event repository dependency"""
    return EventRepository(db)


async def get_tenant_repo(
    db: AsyncSession = Depends(get_db)
) -> TenantRepository:
    """Tenant repository dependency"""
    return TenantRepository(db)


async def get_document_repo(
    db: AsyncSession = Depends(get_db)
) -> DocumentRepository:
    """Document repository dependency"""
    return DocumentRepository(db)


async def get_user_repo(
    db: AsyncSession = Depends(get_db)
) -> UserRepository:
    """User repository dependency"""
    return UserRepository(db)


async def get_event_schema_repo(
    db: AsyncSession = Depends(get_db)
) -> EventSchemaRepository:
    """Event schema repository dependency"""
    return EventSchemaRepository(db)


# Transactional dependencies for write operations
async def get_event_service_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> EventService:
    """Event service dependency with transaction management"""
    return EventService(
        event_repo=EventRepository(db),
        hash_service=HashService(),
        schema_repo=EventSchemaRepository(db)
    )


async def get_subject_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> SubjectRepository:
    """Subject repository dependency with transaction management"""
    return SubjectRepository(db)


async def get_tenant_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> TenantRepository:
    """Tenant repository dependency with transaction management"""
    return TenantRepository(db)


async def get_document_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> DocumentRepository:
    """Document repository dependency with transaction management"""
    return DocumentRepository(db)


async def get_user_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> UserRepository:
    """User repository dependency with transaction management"""
    return UserRepository(db)


async def get_event_schema_repo_transactional(
    db: AsyncSession = Depends(get_db_transactional)
) -> EventSchemaRepository:
    """Event schema repository dependency with transaction management"""
    return EventSchemaRepository(db)

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
        db: AsyncSession = Depends(get_db)
    ) -> TokenPayload:
        authz_service = AuthorizationService(db)
        
        has_permission = await authz_service.check_permission(
            user_id=user.sub,
            tenant_id=user.tenant_id,
            resource=resource,
            action=action
        )
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}:{action} required"
            )
        
        return user
    
    return permission_checker


# Alternative: Inject authorization service for complex checks
async def get_authz_service(
    db: AsyncSession = Depends(get_db)
) -> AuthorizationService:
    """Get authorization service for manual permission checks"""
    return AuthorizationService(db)