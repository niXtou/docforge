"""Async SQLAlchemy engine and session factory.

WHY ASYNC?
──────────
DocForge uses async SQLAlchemy so that database queries do not block the event
loop. In a regular (sync) app, a slow query freezes the whole server. In an
async app, while waiting for Postgres, the event loop can handle other requests.
The asyncpg driver (in DATABASE_URL) is what makes this possible.

HOW SESSIONS WORK
──────────────────
  engine            — a pool of database connections (created once at startup)
  AsyncSessionLocal — a factory that produces new session objects on demand
  get_session()     — a FastAPI dependency that yields one session per request
                      and automatically closes it when the request finishes

A session is like a "unit of work": you add/query objects in it, then commit
to persist changes. If an exception occurs, the session is rolled back and
closed automatically (the `async with` block handles this).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# The engine manages the connection pool. All sessions share this single engine.
# pool_pre_ping=True: before handing out a connection, SQLAlchemy sends a
#   lightweight "SELECT 1" to verify the connection is still alive. This
#   prevents "connection closed" errors after Postgres restarts or idle timeouts.
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,     # if True, prints every SQL statement to the log
    pool_pre_ping=True,
)

# async_sessionmaker is the async equivalent of sessionmaker.
# expire_on_commit=False: by default SQLAlchemy "expires" all ORM objects after
#   a commit, meaning the next access would trigger another DB query. Setting
#   this to False lets us read attributes after committing without extra queries.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    Every model in app/models/db.py inherits from this. SQLAlchemy uses the
    shared metadata on this class to know about all tables in the schema,
    which Alembic then uses to generate migrations.
    """

    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for use as a FastAPI dependency.

    FastAPI calls this generator for each request that declares a `db` parameter.
    The `async with` block guarantees the session is closed even if an exception
    is raised inside the route handler.

    Example usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(MyModel))
    """
    async with AsyncSessionLocal() as session:
        yield session
