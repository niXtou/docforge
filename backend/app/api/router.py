"""Main API router — mounts all sub-routers."""

from fastapi import APIRouter

from app.api import health

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])

# TODO (Stage 3): uncomment when implemented
# api_router.include_router(schemas.router, prefix="/schemas", tags=["schemas"])
# api_router.include_router(documents.router, prefix="/extract", tags=["extraction"])
