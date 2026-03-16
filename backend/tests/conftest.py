"""Pytest fixtures: async DB, mock LLM, test client."""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.core.database import Base
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session", autouse=True)
async def tables() -> AsyncGenerator[None, None]:
    """Create all tables in the in-memory SQLite test database."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for direct DB access in tests."""
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def override_db() -> Generator[None, None, None]:
    """Override get_db dependency to use in-memory SQLite."""

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client for the FastAPI app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
