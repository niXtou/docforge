"""LangGraph workflow state definition."""

# TODO (Stage 2): Build the LangGraph workflow. Complete the learning checkpoints
# in SOURCE_OF_TRUTH.md Section 2.3 before implementing.
#
# from pydantic import BaseModel
#
# class WorkflowState(BaseModel):
#     # Input
#     document_id: str
#     raw_content: str = ""
#     file_type: str = ""
#     schema_definition: dict
#
#     # Processing
#     chunks: list[str] = []
#     current_chunk_index: int = 0
#     chunk_extractions: list[dict] = []
#
#     # Retry tracking
#     retry_count: int = 0
#     max_retries: int = 3
#     last_validation_errors: list[str] = []
#
#     # Output
#     final_result: dict | None = None
#     status: str = "pending"
#     messages: list[str] = []
