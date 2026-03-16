"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ExtractionSchema(Base):
    """Defines a reusable extraction schema (invoice, resume, etc.)."""

    __tablename__ = "extraction_schemas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    json_schema: Mapped[dict[str, object]] = mapped_column(JSON)
    is_builtin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    jobs: Mapped[list["ExtractionJob"]] = relationship(
        back_populates="schema"
    )  # One-to-many relationship: each schema can have multiple extraction jobs


class ExtractionJob(Base):
    """Tracks a single document extraction run."""

    __tablename__ = "extraction_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    schema_id: Mapped[int] = mapped_column(ForeignKey("extraction_schemas.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    original_filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(10))
    model_used: Mapped[str] = mapped_column(String(100))
    result_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    validation_passed: Mapped[bool | None] = mapped_column(nullable=True)
    retries_used: Mapped[int] = mapped_column(default=0)
    processing_time_ms: Mapped[int | None] = mapped_column(nullable=True)
    chunks_processed: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    schema: Mapped["ExtractionSchema"] = relationship(
        back_populates="jobs"
    )  # Many-to-one relationship: each job is associated with one schema
