"""API key validation, model whitelist, and demo rate limiting."""

import redis.asyncio as aioredis
from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.redis import get_redis
from app.models.schemas import ErrorResponse


def check_model_allowed(model: str, api_key: str | None) -> None:
    """Raise HTTP 403 if the model is not allowed in demo mode.

    BYOK users (api_key provided) may use any model.
    Demo users are restricted to settings.demo_allowed_models.
    """
    if api_key:
        return  # BYOK: user supplies their own quota — no restriction
    if model not in settings.demo_allowed_models:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(
                detail=f"Model '{model}' is not available in demo mode. "
                "Provide an api_key to use any model.",
                code="model_not_allowed",
            ).model_dump(),
        )


async def check_demo_rate_limit(client_ip: str, redis: aioredis.Redis) -> None:  # type: ignore[type-arg]
    """Raise HTTP 429 if this IP has exceeded the demo rate limit.

    Uses Redis INCR + EXPIRE to implement a sliding 1-hour window per IP.
    The expire is set only on the first request to avoid resetting the window
    on every call.
    """
    key = f"rl:demo:{client_ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 3600)  # 1-hour window; set only on first request
    if count > settings.demo_rate_limit_per_hour:
        raise HTTPException(
            status_code=429,
            detail=ErrorResponse(
                detail="Rate limit exceeded. Try again later or supply an api_key.",
                code="rate_limit_exceeded",
            ).model_dump(),
        )


async def require_demo_access(request: Request) -> None:
    """FastAPI dependency: enforce model whitelist and demo rate limit.

    Reads form data from the request directly (not via Form() parameter) so
    that it works alongside UploadFile declarations without a duplicate parse.
    FastAPI caches form parsing, so calling request.form() twice is safe.
    """
    form = await request.form()
    api_key = form.get("api_key") or None
    model = str(form.get("model", "google/gemini-2.0-flash-001"))

    check_model_allowed(model, api_key)  # type: ignore[arg-type]

    if not api_key:
        redis = await get_redis()
        client_ip = request.client.host if request.client else "unknown"
        await check_demo_rate_limit(client_ip, redis)
