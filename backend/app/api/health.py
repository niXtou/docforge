"""Health check endpoint."""

import logging

import sqlalchemy.exc
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Return service health including database connectivity.

    Returns:
        dict with status, database, and version fields.
    """
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except sqlalchemy.exc.SQLAlchemyError:
        logger.exception("Database health check failed")
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "error",
        "database": db_status,
        "version": "0.1.0",
    }
