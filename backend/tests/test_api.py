"""API endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    """Health endpoint should return 200 with status field."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "version" in body
