"""FastAPI dependency providers (DB session, auth, rate limiting)."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session to route handlers."""
    async for session in get_session():
        yield session
