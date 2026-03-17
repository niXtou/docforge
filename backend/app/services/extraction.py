"""Extraction service — orchestrates DB job lifecycle and LangGraph workflow.

THIS IS THE GLUE LAYER
───────────────────────
Route handlers (app/api/documents.py) receive HTTP requests and validate
input. The LangGraph workflow (app/workflows/) does the AI processing.
This service sits between them: it manages the database job record and
hands off to the graph.

JOB LIFECYCLE
──────────────
  Route handler creates job_id (UUID) and calls run_extraction()
       │
       ▼
  [DB] Insert ExtractionJob with status="pending"
       │
       ▼
  [DB] Update status → "processing"
       │
       ▼
  [Graph] compiled_graph.ainvoke(state) — runs parse→chunk→extract→validate→merge
       │
       ▼
  [DB] Update job with results, status="completed" (or "failed")
       │
       ▼
  Return ExtractionResult to the route handler

FLUSH VS COMMIT
────────────────
`db.flush()` sends SQL to Postgres but does NOT commit the transaction.
The row is visible to the current session (so we can update it), but no
other session can see it yet. This lets us write "pending" and then
immediately update to "processing" within the same transaction.

`db.commit()` finalises all changes and makes them visible to other sessions.
We commit once at the end (success) or once in the except block (failure),
never mid-workflow.
"""

import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ExtractionJob, ExtractionSchema
from app.models.schemas import ExtractionResult
from app.workflows.graph import compiled_graph
from app.workflows.state import WorkflowState


async def run_extraction(
    job_id: str,
    file_path: str,
    file_type: str,
    original_filename: str,
    schema: ExtractionSchema,
    model: str,
    api_key: str | None,
    db: AsyncSession,
) -> ExtractionResult:
    """Run the extraction pipeline for a document.

    Args:
        job_id: UUID string for this extraction job.
        file_path: Absolute path to the temp file.
        file_type: File extension (e.g. ".pdf").
        original_filename: Original uploaded filename.
        schema: ExtractionSchema ORM object.
        model: OpenRouter model string.
        api_key: BYOK API key or None.
        db: Async database session.

    Returns:
        ExtractionResult with all job metadata.
    """
    # 1. Insert the job record as "pending" so it's immediately visible to
    #    status-polling endpoints, even before processing starts.
    job = ExtractionJob(
        id=job_id,
        schema_id=schema.id,
        status="pending",
        original_filename=original_filename,
        file_type=file_type,
        model_used=model,
    )
    db.add(job)
    await db.flush()  # write to DB without committing — see module docstring

    # 2. Build the initial state that the workflow graph will use.
    #    schema.json_schema is the JSON Schema dict that tells the LLM what to extract.
    state = WorkflowState(
        document_id=job_id,
        file_path=file_path,
        file_type=file_type,
        schema_definition=schema.json_schema,
        model=model,
        api_key=api_key,
    )

    # 3. Mark as processing before handing off to the graph
    job.status = "processing"
    await db.flush()

    # 4. Run the LangGraph workflow.
    #    state.model_dump() converts the Pydantic model to a plain dict — LangGraph
    #    requires this format and reconstructs a typed WorkflowState internally.
    time_start = time.monotonic()
    try:
        result_state: dict = await compiled_graph.ainvoke(state.model_dump())  # type: ignore[assignment]

        elapsed_ms = int((time.monotonic() - time_start) * 1000)

        # Write all results from the final WorkflowState back into the DB record
        job.status = result_state.get("status", "completed")
        job.result_data = result_state.get("final_result")
        job.validation_passed = not bool(result_state.get("last_validation_errors"))
        job.retries_used = result_state.get("retry_count", 0)
        job.processing_time_ms = elapsed_ms
        job.chunks_processed = len(result_state.get("chunks", []))
        job.completed_at = datetime.now(tz=UTC)

        await db.commit()  # persist everything in one transaction

    except Exception as e:
        # If anything in the graph raised, mark the job as failed and re-raise
        # so the route handler can return an appropriate HTTP error.
        job.status = "failed"
        job.error_message = str(e)
        await db.commit()
        raise

    return ExtractionResult(
        job_id=job_id,
        status=job.status,
        data=job.result_data,
        validation_passed=bool(job.validation_passed),
        retries_used=job.retries_used or 0,
        model_used=job.model_used,
        processing_time_ms=job.processing_time_ms or 0,
        chunks_processed=job.chunks_processed or 0,
    )
