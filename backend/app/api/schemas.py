"""Route handlers for extraction schemas CRUD."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.db import ExtractionSchema
from app.models.schemas import SchemaCreate, SchemaResponse

router = APIRouter()


@router.get("", response_model=list[SchemaResponse])
async def list_schemas(db: AsyncSession = Depends(get_db)) -> list[ExtractionSchema]:
    """Return all extraction schemas."""
    result = await db.execute(select(ExtractionSchema))
    return list(result.scalars().all())


@router.get("/{schema_id}", response_model=SchemaResponse)
async def get_schema(schema_id: int, db: AsyncSession = Depends(get_db)) -> ExtractionSchema:
    """Return a single extraction schema by ID."""
    schema = await db.get(ExtractionSchema, schema_id)
    if schema is None:
        raise HTTPException(status_code=404, detail="Schema not found")
    return schema


@router.post("", response_model=SchemaResponse, status_code=201)
async def create_schema(
    payload: SchemaCreate, db: AsyncSession = Depends(get_db)
) -> ExtractionSchema:
    """Create a new extraction schema. Returns 409 on duplicate name."""
    schema = ExtractionSchema(
        name=payload.name,
        description=payload.description,
        json_schema=payload.json_schema,
        is_builtin=False,
    )
    db.add(schema)
    try:
        await db.commit()
        await db.refresh(schema)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Schema name already exists") from None
    return schema
