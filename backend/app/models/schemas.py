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
from typing import Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, Field, field_validator

# ── Request Models ────────────────────────────────────────────────────────────
# These describe what the client sends to the API.


class SchemaCreate(BaseModel):
    """Payload for creating a custom extraction schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Schema name")
    description: str = Field(default="", description="Human-readable description")
    json_schema: dict[str, object] = Field(
        ..., description="JSON Schema defining the extraction target"
    )

    @field_validator("json_schema")
    @classmethod
    def _check_json_schema(cls, value: dict[str, object]) -> dict[str, object]:
        """Reject schemas the workflow could not extract against.

        Runs the JSON-Schema meta-validation, then requires an object schema
        with at least one property — the extraction prompt, consolidate and
        validate nodes all key off ``properties``. Extension keys such as
        ``x-doc-type`` are allowed and passed through untouched.
        """
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as e:
            raise ValueError(f"Invalid JSON Schema: {e.message}") from e
        if value.get("type") != "object":
            raise ValueError("json_schema must have type 'object'")
        properties = value.get("properties")
        if not isinstance(properties, dict) or not properties:
            raise ValueError("json_schema must define a non-empty 'properties' object")
        return value


class ExtractionRequest(BaseModel):
    """Payload for starting a document extraction job.

    Sent alongside the uploaded file as multipart form data.
    The api_key field supports BYOK: users can bring their own OpenRouter key
    to bypass demo rate limits and use their own quota.
    """

    schema_id: int = Field(..., gt=0, description="ID of the extraction schema to use")
    model: str = Field(
        default="google/gemini-3.1-flash-lite",
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


class ExtractionJobSummary(BaseModel):
    """One row of the job history list (GET /api/extract).

    Deliberately excludes the extracted data, the temp file path and the BYOK
    api_key — this is a listing, not a result.
    """

    job_id: str
    status: str
    schema_name: str
    original_filename: str
    model_used: str
    created_at: datetime
    completed_at: datetime | None = None
    processing_time_ms: int | None = None
    retries_used: int
    validation_passed: bool | None = None  # None until the workflow has run


class FieldEvidence(BaseModel):
    """Provenance for one extracted value: where in the document it was verified.

    ``method`` says how the value was grounded — found verbatim in the source,
    accepted by the LLM judge, or not checkable (numbers that were reformatted,
    or a value the judge returned no verdict for). ``supported`` is False only
    for values the judge rejected; those are nulled/dropped from ``data``.
    """

    quote: str = Field(description="Snippet of the document the value was verified against")
    method: Literal["verbatim", "judge", "unverified"]
    supported: bool


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
    error_message: str | None = None  # populated when status == "failed"
    # Errors from the final validation pass; empty when validation passed.
    validation_errors: list[str] = []
    # Per-field provenance keyed by field name, or "field[idx]" for array items.
    evidence: dict[str, FieldEvidence] = {}

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
      node_completed    — a workflow node finished. `data` always carries
                          `keys_updated`; some nodes add more:
                            chunk            → chunks (int)
                            extract          → chunks (int, chunk extractions)
                            verify_grounding → issues (list[str]), evidence_count (int)
                            validate         → errors (list[str]), attempt (int)
      progress          — fine-grained within-node progress; `data` has
                          node, completed, total
      retry             — validation failed and extraction is being re-run.
                          node="validate"; `data` has attempt (int) and
                          errors (list[str]) — the feedback fed to the model
      error             — an unrecoverable error occurred
      done              — the workflow finished; `data` has the final status
    """

    event: str = Field(
        ...,
        description="node_completed | progress | retry | error | done",
    )
    node: str | None = None  # which graph node (parse, chunk, extract, …)
    message: str
    timestamp: datetime
    data: dict[str, object] | None = None
