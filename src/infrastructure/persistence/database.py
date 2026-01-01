from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.orm import DeclarativeBase

from src.infrastructure.config.settings import get_settings

settings = get_settings()

# Create engine once at module level (not with lru_cache)
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=30,
    pool_recycle=3600,
    query_cache_size=1200,
    connect_args=(
        {
            "server_settings": {"jit": "off"},
            "command_timeout": 60,
        }
        if "postgresql" in settings.database_url
        else {}
    ),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# Modern SQLAlchemy 2.0 pattern
class Base(DeclarativeBase):
    """Base class for all database models"""

    pass


async def get_db():
    """
    Database session dependency for read operations.
    Does not commit - read-only operations don't need commits.
    Write operations should use get_db_transactional().

    Note: async with context manager handles session cleanup automatically.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_db_transactional():
    """
    Database session dependency for write operations with automatic transaction management.
    - Begins transaction automatically
    - Commits on success
    - Rolls back on exception
    - Closes session automatically

    Use this for POST, PUT, PATCH, DELETE endpoints.
    """
    async with AsyncSessionLocal() as session:
        try:
            async with session.begin():
                yield session
        except Exception:
            await session.rollback()
            raise
