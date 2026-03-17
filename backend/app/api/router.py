"""Main API router — mounts all sub-routers under /api.

ROUTING STRUCTURE
──────────────────
  /api/health        — liveness and DB connectivity check (this stage)
  /api/schemas       — CRUD for extraction schemas         (Stage 3)
  /api/extract       — document upload and job management  (Stage 3)

Routes are added incrementally as each stage is implemented. The TODOs below
act as placeholders so the final URL layout is visible from day one.

Each sub-router lives in its own file (health.py, schemas.py, documents.py)
so endpoints stay focused and easy to find.
"""

from fastapi import APIRouter

from app.api import health

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])

# TODO (Stage 3): uncomment when implemented
# api_router.include_router(schemas.router, prefix="/schemas", tags=["schemas"])
# api_router.include_router(documents.router, prefix="/extract", tags=["extraction"])
