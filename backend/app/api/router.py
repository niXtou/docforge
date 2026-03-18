"""Main API router — mounts all sub-routers under /api.

ROUTING STRUCTURE
──────────────────
  /api/health        — liveness and DB connectivity check
  /api/schemas       — CRUD for extraction schemas
  /api/extract       — document upload and job management

Each sub-router lives in its own file (health.py, schemas.py, documents.py)
so endpoints stay focused and easy to find.
"""

from fastapi import APIRouter

from app.api import documents, health, schemas

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(schemas.router, prefix="/schemas", tags=["schemas"])
api_router.include_router(documents.router, prefix="/extract", tags=["extraction"])
