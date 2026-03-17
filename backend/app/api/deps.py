"""FastAPI dependency providers (DB session, auth, rate limiting).

WHAT IS DEPENDENCY INJECTION?
──────────────────────────────
FastAPI has a built-in dependency injection system. Instead of each route
handler creating its own database session, it declares that it *needs* one,
and FastAPI calls the appropriate provider function and passes the result in.

Example:
    async def my_route(db: AsyncSession = Depends(get_db)):
        # FastAPI called get_db(), got a session, and injected it here.
        # After the route returns, FastAPI resumes get_db() after the yield,
        # which closes the session automatically.
        ...

Benefits:
  - Routes don't need to know how sessions are created or closed.
  - In tests, you can replace get_db with a test-database version by setting
    app.dependency_overrides[get_db] = my_test_get_db — no code changes needed.

WHY A SEPARATE FILE?
─────────────────────
Keeping deps.py separate from the route handlers prevents circular imports
(routes import deps, not the other way around) and makes it easy to add
more dependencies (auth, rate limiting) as the app grows.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session to route handlers.

    This thin wrapper delegates to get_session() from core/database.py.
    Route handlers depend on get_db (not get_session directly) so that
    tests can override get_db without touching core infrastructure.
    """
    async for session in get_session():
        yield session
