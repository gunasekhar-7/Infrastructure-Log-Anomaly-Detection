"""Async Database Connection Engine and Session Management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.logging import get_logger
from config.settings import settings
from src.database.models import Base

logger = get_logger("database_connection")

# Global async engine instance
_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create singleton AsyncEngine."""
    global _engine
    if _engine is None:
        db_url = settings.DATABASE_URL
        # SQLite async requires check_same_thread=False
        connect_args = {}
        if "sqlite" in db_url:
            connect_args["check_same_thread"] = False

        _engine = create_async_engine(
            db_url,
            echo=settings.DB_ECHO,
            future=True,
            connect_args=connect_args,
        )
        logger.info("Initialized AsyncEngine for %s", db_url.split("@")[-1])
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create singleton async_sessionmaker."""
    global _session_maker
    if _session_maker is None:
        engine = get_engine()
        _session_maker = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_maker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an active AsyncSession."""
    session_factory = get_session_maker()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database schema by creating all tables asynchronously if not present."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized successfully.")


async def close_db() -> None:
    """Dispose database connection pool gracefully."""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_maker = None
        logger.info("Database engine closed.")

