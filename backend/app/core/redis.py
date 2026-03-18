"""Lazy Redis client singleton.

Mirrors the database.py pattern: one shared client created on first use.
Use get_redis() as a FastAPI dependency or call it directly in services.
"""

import redis.asyncio as aioredis

from app.core.config import settings

_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


async def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    """Return the shared Redis client, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection (called during app shutdown)."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
