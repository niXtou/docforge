"""LangGraph workflow state definition."""

from pydantic import BaseModel


class WorkflowState(BaseModel):
    # Input
    document_id: str  # job UUID (log key)
    file_path: str = ""  # absolute temp path — parse node reads this
    raw_content: str = ""
    file_type: str = ""
    schema_definition: dict  # type: ignore[type-arg]  # JSON Schema from user
    model: str = "anthropic/claude-sonnet-4-20250514"
    api_key: str | None = None  # BYOK

    # Processing
    chunks: list[str] = []
    current_chunk_index: int = 0
    chunk_extractions: list[dict] = []  # type: ignore[type-arg]

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    last_validation_errors: list[str] = []

    # Output
    final_result: dict | None = None  # type: ignore[type-arg]
    status: str = "pending"
    messages: list[str] = []
