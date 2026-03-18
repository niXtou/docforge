"""FastAPI application factory with lifespan management.

HOW A REQUEST FLOWS THROUGH DOCFORGE
─────────────────────────────────────
  HTTP request
      │
      ▼
  CORSMiddleware          — checks the Origin header; blocks disallowed origins
      │
      ▼
  api_router (/api/...)   — routes to the correct endpoint function
      │
      ▼
  Dependency injection    — FastAPI calls get_db() and injects a DB session
      │
      ▼
  Route handler           — validates input, calls a service function
      │
      ▼
  Service / LangGraph     — runs the extraction workflow, writes DB records
      │
      ▼
  Response                — Pydantic serialises the return value to JSON

FILE LAYOUT
───────────
  app/core/       — config, database engine, LLM factory
  app/api/        — route handlers and FastAPI dependency functions
  app/models/     — SQLAlchemy ORM models (db.py) and Pydantic schemas (schemas.py)
  app/workflows/  — LangGraph state, nodes, and compiled graph
  app/services/   — orchestration layer between routes and the workflow
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.redis import close_redis
from app.models.db import ExtractionSchema

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Built-in schemas shipped with the app.
_BUILTIN_SCHEMAS = [
    {
        "name": "Invoice",
        "description": "Extract key fields from an invoice document.",
        "json_schema": {
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string"},
                "total_amount": {"type": "number"},
                "vendor_name": {"type": "string"},
                "invoice_date": {"type": "string"},
            },
            "required": ["invoice_number", "total_amount"],
        },
    },
    {
        "name": "Resume/CV",
        "description": "Extract key fields from a resume or CV.",
        "json_schema": {
            "type": "object",
            "properties": {
                "full_name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "skills": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["full_name"],
        },
    },
    {
        "name": "Research Paper",
        "description": "Extract key fields from an academic research paper.",
        "json_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "authors": {"type": "array", "items": {"type": "string"}},
                "abstract": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "authors", "abstract"],
        },
    },
]


async def seed_builtin_schemas(session: AsyncSession) -> None:
    """Insert built-in schemas if they don't already exist.

    Checks by name before inserting so re-running on an already-seeded DB is safe.
    Importable so tests can call it directly without going through the lifespan.
    """
    for schema_def in _BUILTIN_SCHEMAS:
        existing = await session.execute(
            select(ExtractionSchema).where(ExtractionSchema.name == schema_def["name"])
        )
        if existing.scalar_one_or_none() is None:
            session.add(
                ExtractionSchema(
                    name=schema_def["name"],
                    description=schema_def["description"],
                    json_schema=schema_def["json_schema"],
                    is_builtin=True,
                )
            )
    await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown events.

    Using a lifespan context manager (instead of the older @app.on_event
    decorators) is the modern FastAPI approach. Code before `yield` runs on
    startup; code after `yield` runs on shutdown.

    On shutdown we explicitly dispose the database engine so all pooled
    connections are closed cleanly — important when running multiple workers.
    """
    logger.info("DocForge starting up")
    async with AsyncSessionLocal() as session:
        await seed_builtin_schemas(session)
    yield
    await close_redis()
    await engine.dispose()  # drain the SQLAlchemy connection pool
    logger.info("DocForge shutting down")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application.

    Using a factory function (rather than a bare module-level `app = FastAPI()`)
    makes it easy to create test instances with different settings.
    """
    app = FastAPI(
        title="DocForge",
        description="AI-powered document intelligence API",
        version="0.1.0",
        docs_url="/docs",  # Swagger UI — http://localhost:8000/docs
        redoc_url="/redoc",  # ReDoc UI  — http://localhost:8000/redoc
        lifespan=lifespan,
    )

    # CORS (Cross-Origin Resource Sharing): browsers block requests from one
    # origin (e.g. http://localhost:5173) to another (http://localhost:8000)
    # unless the server explicitly allows it. This middleware adds the required
    # "Access-Control-Allow-*" headers to every response.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Mount all API routes under the /api prefix (e.g. /api/health)
    app.include_router(api_router, prefix="/api")

    return app


# Module-level app instance — this is what uvicorn imports: `app.main:app`
app = create_app()
