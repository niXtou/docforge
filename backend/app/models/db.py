"""SQLAlchemy ORM models — the database table definitions.

WHAT IS AN ORM?
────────────────
ORM (Object-Relational Mapper) lets you work with database rows as Python
objects instead of writing raw SQL. SQLAlchemy is the ORM used here.

Each class = one database table. Each class attribute = one column.
The `Mapped[type]` annotation tells SQLAlchemy (and the type-checker) what
Python type to use when reading that column back from the database.

HOW TABLES RELATE
──────────────────
  ExtractionSchema  ──┐  one schema can have many jobs
                      │  (stored as schema_id foreign key on the job)
  ExtractionJob    ◄──┘

The `relationship()` calls let you navigate between objects in Python:
  schema.jobs       → list of ExtractionJob objects for this schema
  job.schema        → the ExtractionSchema object for this job

DATABASE MIGRATIONS
────────────────────
When you add/change a column here, run `alembic revision --autogenerate`
to generate a migration script, then `alembic upgrade head` to apply it.
Never modify the database directly — always go through Alembic.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ExtractionSchema(Base):
    """Defines a reusable extraction schema (invoice, resume, etc.).

    A schema is a JSON Schema document that tells the LLM what fields to
    extract from a document. Users create schemas once and reuse them across
    many extraction jobs.

    Example json_schema for an invoice:
        {
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string"},
                "total_amount":   {"type": "number"}
            },
            "required": ["invoice_number", "total_amount"]
        }
    """

    __tablename__ = "extraction_schemas"

    id: Mapped[int] = mapped_column(primary_key=True)  # auto-incremented by Postgres
    name: Mapped[str] = mapped_column(String(100), unique=True)  # human-readable identifier
    description: Mapped[str] = mapped_column(Text, default="")
    json_schema: Mapped[dict[str, object]] = mapped_column(JSON)  # stored as a JSON column
    is_builtin: Mapped[bool] = mapped_column(default=False)  # True = shipped with the app
    # server_default=func.now() means Postgres sets this, not Python — avoids clock skew
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # One-to-many: one schema → many jobs. SQLAlchemy populates this list
    # automatically when you access schema.jobs (lazy loads from DB).
    jobs: Mapped[list["ExtractionJob"]] = relationship(back_populates="schema")


class ExtractionJob(Base):
    """Tracks a single document extraction run.

    Each time a user uploads a document, one ExtractionJob is created.
    Its status moves through: pending → processing → completed / failed.
    The final extracted data is stored in result_data as a JSON blob.
    """

    __tablename__ = "extraction_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID (caller provides it)
    schema_id: Mapped[int] = mapped_column(ForeignKey("extraction_schemas.id"))  # which schema
    # Status lifecycle: "pending" → "processing" → "completed" | "completed_with_errors" | "failed"
    status: Mapped[str] = mapped_column(String(50), default="pending")
    original_filename: Mapped[str] = mapped_column(String(255))  # e.g. "invoice_jan.pdf"
    file_type: Mapped[str] = mapped_column(String(10))  # e.g. ".pdf"
    model_used: Mapped[str] = mapped_column(String(100))  # OpenRouter model string

    # Populated after the LangGraph workflow completes:
    result_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    validation_passed: Mapped[bool | None] = mapped_column(nullable=True)  # None = not yet run
    retries_used: Mapped[int] = mapped_column(default=0)
    processing_time_ms: Mapped[int | None] = mapped_column(nullable=True)
    chunks_processed: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # set on failure
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)  # set on completion

    # Stage 3: two-phase upload→stream design
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=func.now())
    file_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # temp file for SSE handler
    api_key: Mapped[str | None] = mapped_column(String(200), nullable=True)  # BYOK stored for SSE

    # Many-to-one: each job belongs to one schema.
    schema: Mapped["ExtractionSchema"] = relationship(back_populates="jobs")
