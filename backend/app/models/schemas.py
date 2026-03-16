"""Pydantic request/response models for the API."""

from datetime import datetime

from pydantic import BaseModel, Field

# --- Request Models ---


class SchemaCreate(BaseModel):
    """Payload for creating a custom extraction schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Schema name")
    description: str = Field(default="", description="Human-readable description")
    json_schema: dict = Field(..., description="JSON Schema defining the extraction target")


class ExtractionRequest(BaseModel):
    """Payload for starting a document extraction job."""

    schema_id: int = Field(..., gt=0, description="ID of the extraction schema to use")
    model: str = Field(
        default="anthropic/claude-sonnet-4-20250514",
        min_length=1,
        description="OpenRouter model string",
    )
    api_key: str | None = Field(
        default=None,
        description="BYOK — user's OpenRouter API key. Uses server key if omitted.",
    )


# --- Response Models ---


class SchemaResponse(BaseModel):
    """API response for a single extraction schema."""

    id: int
    name: str
    description: str
    json_schema: dict
    is_builtin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractionJobResponse(BaseModel):
    """API response for a created extraction job."""

    job_id: str
    status: str
    schema_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExtractionResult(BaseModel):
    """Full extraction result returned after job completion."""

    job_id: str
    status: str
    data: dict | None
    validation_passed: bool
    retries_used: int
    model_used: str
    processing_time_ms: int
    chunks_processed: int

    model_config = {"from_attributes": True}


class StreamEvent(BaseModel):
    """SSE event payload emitted per LangGraph node transition."""

    event: str = Field(
        ...,
        description="node_started | node_completed | retry | error | done",
    )
    node: str | None = None
    message: str
    timestamp: datetime
    data: dict | None = None
