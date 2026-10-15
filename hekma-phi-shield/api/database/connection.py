import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text
from api.config.settings import settings

logger = logging.getLogger("pii-phi.db")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        _engine = create_async_engine(
            db_url,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_pre_ping=True,
            pool_recycle=1800,
            echo=settings.DB_ECHO,
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        logger.info("Initialized Async PostgreSQL engine for Token Vault")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db_schema() -> None:
    """Creates database tables automatically if they do not exist and applies safe migrations."""
    from api.database.models import Base
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        migrations = [
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS contact_email VARCHAR(256);",
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS raw_api_key_preview VARCHAR(128);",
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS audit_retention_days INTEGER DEFAULT 0;",
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS token_ttl_days INTEGER DEFAULT 0;",
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS settings_json TEXT DEFAULT '{}';",
            "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
        ]
        for m in migrations:
            try:
                await conn.execute(text(m))
            except Exception as e:
                logger.debug("Migration query note (%s): %s", m, e)
    logger.info("PostgreSQL database schema verified / initialized")


async def check_db_health() -> bool:
    """Verifies active connectivity to the PostgreSQL Token Vault."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("PostgreSQL database health check failed: %s", e)
        return False


async def close_db_connections() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Closed PostgreSQL Token Vault connection pool")
