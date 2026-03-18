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
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ExtractionJob, ExtractionSchema
from app.models.schemas import ExtractionResult, StreamEvent
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


async def create_job(
    job_id: str,
    schema_id: int,
    original_filename: str,
    file_type: str,
    model: str,
    file_path: str,
    api_key: str | None,
    db: AsyncSession,
) -> ExtractionJob:
    """Insert a new ExtractionJob row with status='pending' and return it.

    Called by POST /api/extract immediately after the file is saved.
    The job stays 'pending' until the client connects to the SSE endpoint.
    """
    job = ExtractionJob(
        id=job_id,
        schema_id=schema_id,
        status="pending",
        original_filename=original_filename,
        file_type=file_type,
        model_used=model,
        file_path=file_path,
        api_key=api_key,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def stream_extraction(
    job: ExtractionJob,
    db: AsyncSession,
) -> AsyncGenerator[StreamEvent, None]:
    """Run the LangGraph workflow and yield one StreamEvent per node.

    This is the SSE worker: it drives the graph and emits progress events.
    Results are written back to the DB after the loop completes.
    The temp file is cleaned up in the finally block regardless of outcome.
    """
    schema_obj = await db.get(ExtractionSchema, job.schema_id)
    if schema_obj is None:
        yield StreamEvent(
            event="error",
            node=None,
            message=f"Schema {job.schema_id} not found",
            timestamp=datetime.now(tz=UTC),
        )
        return

    state = WorkflowState(
        document_id=job.id,
        file_path=job.file_path or "",
        file_type=job.file_type,
        schema_definition=schema_obj.json_schema,
        model=job.model_used,
        api_key=job.api_key,
    )
    job.status = "processing"
    await db.commit()

    final_state: dict[str, object] = {}
    time_start = time.monotonic()
    try:
        async for update in compiled_graph.astream(state.model_dump()):  # type: ignore[arg-type]
            for node_name, node_output in update.items():
                final_state.update(node_output)  # type: ignore[arg-type]
                yield StreamEvent(
                    event="node_completed",
                    node=node_name,
                    message=f"Node '{node_name}' completed",
                    timestamp=datetime.now(tz=UTC),
                    data={"keys_updated": list(node_output.keys())},  # type: ignore[union-attr]
                )

        elapsed_ms = int((time.monotonic() - time_start) * 1000)
        job.status = str(final_state.get("status", "completed"))
        job.result_data = final_state.get("final_result")  # type: ignore[assignment]
        job.validation_passed = not bool(final_state.get("last_validation_errors"))
        job.retries_used = int(final_state.get("retry_count", 0))  # type: ignore[arg-type]
        job.processing_time_ms = elapsed_ms
        job.chunks_processed = len(list(final_state.get("chunks", [])))  # type: ignore[arg-type]
        job.completed_at = datetime.now(tz=UTC)
        await db.commit()
        yield StreamEvent(
            event="done",
            node=None,
            message="Extraction complete",
            timestamp=datetime.now(tz=UTC),
            data={"status": job.status},
        )
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        await db.commit()
        yield StreamEvent(
            event="error",
            node=None,
            message=str(e),
            timestamp=datetime.now(tz=UTC),
        )
    finally:
        if job.file_path:
            Path(job.file_path).unlink(missing_ok=True)
