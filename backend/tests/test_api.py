"""API endpoint tests."""

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    """Health endpoint should return 200 with status field."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


async def test_health_db_error(client: AsyncClient) -> None:
    """Health endpoint should return status=error when DB execute fails."""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy.exc import SQLAlchemyError

    from app.api.deps import get_db
    from app.main import app

    # Build a mock session whose execute() raises a SQLAlchemyError so that
    # the health handler catches it and returns status="error".
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(side_effect=SQLAlchemyError("DB is down"))

    async def broken_db():
        yield mock_session

    app.dependency_overrides[get_db] = broken_db
    try:
        response = await client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
    finally:
        app.dependency_overrides.pop(get_db, None)
