"""Extraction service — orchestrates DB job lifecycle and LangGraph workflow."""

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
    # 1. Create the job record
    job = ExtractionJob(
        id=job_id,
        schema_id=schema.id,
        status="pending",
        original_filename=original_filename,
        file_type=file_type,
        model_used=model,
    )
    db.add(job)
    await db.flush()

    # 2. Build initial workflow state
    state = WorkflowState(
        document_id=job_id,
        file_path=file_path,
        file_type=file_type,
        schema_definition=schema.json_schema,
        model=model,
        api_key=api_key,
    )

    # 3. Update status to processing
    job.status = "processing"
    await db.flush()

    # 4. Run the graph
    time_start = time.monotonic()
    try:
        result_state: dict = await compiled_graph.ainvoke(state.model_dump())  # type: ignore[assignment]

        elapsed_ms = int((time.monotonic() - time_start) * 1000)

        job.status = result_state.get("status", "completed")
        job.result_data = result_state.get("final_result")
        job.validation_passed = not bool(result_state.get("last_validation_errors"))
        job.retries_used = result_state.get("retry_count", 0)
        job.processing_time_ms = elapsed_ms
        job.chunks_processed = len(result_state.get("chunks", []))
        job.completed_at = datetime.now(tz=UTC)

        await db.commit()

    except Exception as e:
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
