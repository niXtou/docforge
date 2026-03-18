"""Pydantic request/response models for the API.

WHY TWO SETS OF MODELS?
────────────────────────
This file contains Pydantic models (for the API boundary), while app/models/db.py
contains SQLAlchemy models (for the database). They are intentionally separate:

  - Pydantic models validate and serialise HTTP request/response data.
    They control exactly what fields the API accepts and returns.
  - SQLAlchemy models map to database tables and may contain columns you don't
    want to expose (internal flags, foreign keys, etc.).

Keeping them separate means a change to the database schema doesn't
accidentally leak into the API contract, and vice versa.

`from_attributes = True` (in model_config) tells Pydantic it can read
attribute values from SQLAlchemy ORM objects, not just plain dicts. This
is what allows `ExtractionResult.model_validate(job_orm_object)` to work.
"""

from datetime import datetime

from pydantic import BaseModel, Field

# ── Request Models ────────────────────────────────────────────────────────────
# These describe what the client sends to the API.


class SchemaCreate(BaseModel):
    """Payload for creating a custom extraction schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Schema name")
    description: str = Field(default="", description="Human-readable description")
    json_schema: dict[str, object] = Field(
        ..., description="JSON Schema defining the extraction target"
    )


class ExtractionRequest(BaseModel):
    """Payload for starting a document extraction job.

    Sent alongside the uploaded file as multipart form data.
    The api_key field supports BYOK: users can bring their own OpenRouter key
    to bypass demo rate limits and use their own quota.
    """

    schema_id: int = Field(..., gt=0, description="ID of the extraction schema to use")
    model: str = Field(
        default="google/gemini-2.0-flash",
        min_length=1,
        description="OpenRouter model string",
    )
    api_key: str | None = Field(
        default=None,
        description="BYOK — user's OpenRouter API key. Uses server key if omitted.",
    )


# ── Response Models ───────────────────────────────────────────────────────────
# These describe what the API sends back to the client.


class SchemaResponse(BaseModel):
    """API response for a single extraction schema."""

    id: int
    name: str
    description: str
    json_schema: dict[str, object]
    is_builtin: bool
    created_at: datetime

    model_config = {"from_attributes": True}  # can be built from an ORM object


class ExtractionJobResponse(BaseModel):
    """API response for a created extraction job (returned immediately on upload)."""

    job_id: str
    status: str
    schema_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractionResult(BaseModel):
    """Full extraction result returned after job completion.

    Clients poll GET /api/extract/{job_id}/result until status is
    "completed", "completed_with_errors", or "failed".
    """

    job_id: str
    status: str
    data: dict[str, object] | None  # the extracted fields; None if job failed
    validation_passed: bool
    retries_used: int
    model_used: str
    processing_time_ms: int
    chunks_processed: int

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str
    code: str | None = None  # e.g. "rate_limit_exceeded", "model_not_allowed"


class StreamEvent(BaseModel):
    """SSE event payload emitted per LangGraph node transition.

    SSE (Server-Sent Events) lets the server push updates to the client
    over a long-lived HTTP connection. As the LangGraph workflow moves
    through nodes, it emits one StreamEvent per transition.

    The `event` field indicates what happened:
      node_started      — a workflow node began executing
      node_completed    — a workflow node finished
      retry             — validation failed; re-running extraction
      error             — an unrecoverable error occurred
      done              — the workflow finished (success or failure)
    """

    event: str = Field(
        ...,
        description="node_started | node_completed | retry | error | done",
    )
    node: str | None = None  # which graph node (parse, chunk, extract, …)
    message: str
    timestamp: datetime
    data: dict[str, object] | None = None
