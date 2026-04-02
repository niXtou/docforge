"""Extraction service — orchestrates DB job lifecycle and LangGraph workflow.

THIS IS THE GLUE LAYER
───────────────────────
Route handlers (app/api/documents.py) receive HTTP requests and validate
input. The LangGraph workflow (app/workflows/) does the AI processing.
This service sits between them: it manages the database job record and
hands off to the graph.

JOB LIFECYCLE — SSE PATH (stream_extraction / _run_extraction_task)
──────────────────────────────────────────────────────────────────────
  POST /api/extract saves file + calls create_job() → status="pending"
       │
       ▼
  GET /api/extract/{id}/stream calls stream_extraction()
       │
       ├─ [DB] commit status="processing"  (request session)
       │
       └─ asyncio.create_task(_run_extraction_task(...))
              │  (background task, owns its own DB session)
              ▼
         [Graph] compiled_graph.astream() — yields one update per node
              │    each update → queue.put(StreamEvent)
              ▼
         [DB] commit final results, status="completed"/"failed"
              │
              └─ queue.put(None)  ← sentinel: SSE generator stops

  SSE generator reads from queue and yields to client.
  Background task is NOT cancelled if the client disconnects — it
  commits results independently so the job is always finalisable.

FLUSH VS COMMIT
──────────────────────────────────
`db.flush()` sends SQL to Postgres but does NOT commit the transaction.
The row is visible to the current session (so we can update it), but no
other session can see it yet. This lets us write "pending" and then
immediately update to "processing" within the same transaction.

`db.commit()` finalises all changes and makes them visible to other sessions.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.db import ExtractionJob, ExtractionSchema
from app.models.schemas import StreamEvent
from app.workflows.graph import compiled_graph
from app.workflows.state import WorkflowState

logger = logging.getLogger(__name__)


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


async def _run_extraction_task(
    job_id: str,
    state: WorkflowState,
    file_path: str | None,
    queue: "asyncio.Queue[StreamEvent | None]",
) -> None:
    """Background task: runs the LangGraph graph and writes results to the DB.

    Uses its own DB session so it continues to completion even if the SSE
    connection is closed (the task is created with asyncio.create_task and
    runs independently of the SSE generator lifecycle).
    """
    final_state: dict[str, object] = {}
    time_start = time.monotonic()
    prefix = f"[Job {job_id}]"

    async with AsyncSessionLocal() as task_db:
        try:
            async for update in compiled_graph.astream(
                state.model_dump(),  # type: ignore[arg-type]
                stream_mode="updates",
            ):
                for node_name, node_output in update.items():
                    final_state.update(node_output)  # type: ignore[arg-type]
                    logger.debug("%s Node '%s' completed", prefix, node_name)
                    await queue.put(
                        StreamEvent(
                            event="node_completed",
                            node=node_name,
                            message=f"Node '{node_name}' completed",
                            timestamp=datetime.now(tz=UTC),
                            data={"keys_updated": list(node_output.keys())},  # type: ignore[union-attr]
                        )
                    )

            elapsed_ms = int((time.monotonic() - time_start) * 1000)
            job = await task_db.get(ExtractionJob, job_id)
            if job is not None:
                job.status = str(final_state.get("status", "completed"))
                job.result_data = final_state.get("final_result")  # type: ignore[assignment]
                job.validation_passed = not bool(final_state.get("last_validation_errors"))
                job.retries_used = int(final_state.get("retry_count", 0))  # type: ignore[arg-type]
                job.processing_time_ms = elapsed_ms
                job.chunks_processed = len(list(final_state.get("chunks", [])))  # type: ignore[arg-type]
                job.completed_at = datetime.now(UTC).replace(
                    tzinfo=None
                )  # TIMESTAMP WITHOUT TIME ZONE
                await task_db.commit()
                logger.info("%s Completed with status: %s", prefix, job.status)
            else:
                logger.warning("%s Job not found in DB after graph completed", prefix)

            await queue.put(
                StreamEvent(
                    event="done",
                    node=None,
                    message="Extraction complete",
                    timestamp=datetime.now(tz=UTC),
                    data={"status": str(final_state.get("status", "completed"))},
                )
            )
        except Exception as e:
            logger.exception("%s Failed: %s", prefix, e)
            try:
                job = await task_db.get(ExtractionJob, job_id)
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(e)
                    await task_db.commit()
            except Exception:
                logger.exception("%s Failed to mark job as failed", prefix)

            await queue.put(
                StreamEvent(
                    event="error",
                    node=None,
                    message=str(e),
                    timestamp=datetime.now(tz=UTC),
                )
            )
        finally:
            # 1. Clear sensitive api_key from DB now that job is terminal
            try:
                job = await task_db.get(ExtractionJob, job_id)
                if job and job.api_key:
                    job.api_key = None
                    await task_db.commit()
                    logger.debug("%s Sensitive api_key purged from DB", prefix)
            except Exception:
                logger.warning("%s Failed to purge api_key", prefix)

            # 2. Signal the SSE generator that we're done
            await queue.put(None)

            # 3. Clean up temp file
            if file_path:
                Path(file_path).unlink(missing_ok=True)
                logger.debug("%s Temp file unlinked: %s", prefix, file_path)


async def stream_extraction(
    job: ExtractionJob,
    db: AsyncSession,
) -> AsyncGenerator[StreamEvent, None]:
    """Start the extraction as a background task and stream progress events via SSE.

    DESIGN: The LangGraph execution runs in a separate asyncio.Task with its own
    DB session. This decouples the DB commit from the SSE connection lifecycle:
    even if the client disconnects, the background task continues to completion
    and writes the result to the DB. The SSE generator simply reads events from
    a shared queue until it receives the sentinel (None).
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

    # Mark as processing in the request's session (fast — no graph involved)
    job.status = "processing"
    await db.commit()

    # Hand off to the background task which owns its own session from here on
    queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
    task = asyncio.create_task(_run_extraction_task(job.id, state, job.file_path, queue))
    logger.info("Started background extraction task for job %s", job.id)

    try:
        while True:
            event = await queue.get()
            if event is None:
                # Sentinel: background task is done
                break
            yield event
    finally:
        # If the SSE client disconnected early, the task is still running.
        # We deliberately do NOT cancel it — it will commit results on its own.
        if task.done():
            try:
                if exc := task.exception():
                    logger.error("Background extraction task for job %s raised: %s", job.id, exc)
            except asyncio.CancelledError:
                pass  # task was cancelled during shutdown — not an error
