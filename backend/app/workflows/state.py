"""LangGraph workflow state definition.

WHAT IS WORKFLOWSTATE?
───────────────────────
WorkflowState is the "shared notebook" that gets passed between every node
in the LangGraph workflow. Think of it as a document that each node reads
from and writes to. When a node finishes, it returns a dict of fields it
wants to update — LangGraph merges those updates into the state and passes
the updated state to the next node.

Because it's a Pydantic model, all fields are type-validated at creation
and can be serialised to a plain dict (via .model_dump()) for storage or
passing across process boundaries.

THE RETRY LOOP AND HOW STATE DRIVES IT
────────────────────────────────────────
The graph has one conditional loop: after validation, the router checks
`last_validation_errors` and `retry_count` to decide whether to retry:

  validate_extraction → sets last_validation_errors + increments retry_count
  route_after_validate → reads those two fields to decide "merge" vs "extract"
  extract_structured → on retry, reads last_validation_errors to improve prompt

So the state is both the data pipeline (raw text → chunks → extractions)
and the control signal (retry_count tells nodes they're in a retry pass).

FIELD GROUPS AT A GLANCE
─────────────────────────
  Input      — set by the caller before the graph starts; never changed by nodes
  Processing — filled in and modified as the graph runs
  Retry      — updated by validate_extraction; read by route_after_validate
  Output     — set by merge_extractions at the very end
"""

from pydantic import BaseModel


class WorkflowState(BaseModel):
    # ── Input ─────────────────────────────────────────────────────────────────
    # Set once by the caller (extraction service) before the graph starts.

    document_id: str        # job UUID — used as a log key to correlate all log lines
    file_path: str = ""     # absolute path to the uploaded temp file on disk
    raw_content: str = ""   # filled in by parse_document; empty until then
    file_type: str = ""     # e.g. ".pdf" — set by caller or detected by parse_document
    schema_definition: dict  # type: ignore[type-arg]  # JSON Schema the LLM must conform to
    model: str = "google/gemini-2.0-flash"  # OpenRouter model string
    api_key: str | None = None  # BYOK key; None = use the server's OpenRouter key

    # ── Processing ────────────────────────────────────────────────────────────
    # Updated by individual nodes as the document moves through the pipeline.

    chunks: list[str] = []                     # set by chunk_text; one entry per chunk
    current_chunk_index: int = 0               # reserved for future streaming progress
    chunk_extractions: list[dict] = []         # type: ignore[type-arg]  # one dict per chunk, set by extract_structured

    # ── Retry tracking ────────────────────────────────────────────────────────
    # These two fields form the control signal for the retry loop.
    # validate_extraction writes to them; route_after_validate reads them.

    retry_count: int = 0               # how many extraction retries have happened so far
    max_retries: int = 3               # give up and proceed to merge after this many retries
    last_validation_errors: list[str] = []  # populated by validate_extraction on failure;
                                            # prepended to the LLM prompt on the next retry

    # ── Output ────────────────────────────────────────────────────────────────
    # Set by merge_extractions at the end of the graph run.

    final_result: dict | None = None   # type: ignore[type-arg]  # the merged extraction dict
    status: str = "pending"            # "completed" | "completed_with_errors" | "failed"
    messages: list[str] = []           # human-readable log of what each node did
