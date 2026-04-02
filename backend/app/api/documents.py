"""Route handlers for document upload and extraction."""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_db
from app.core.security import require_demo_access
from app.models.db import ExtractionJob, ExtractionSchema
from app.models.schemas import ExtractionJobResponse, ExtractionResult, StreamEvent
from app.services.extraction import create_job, stream_extraction

router = APIRouter()

# Jobs that are already in a terminal state — no need to re-run the graph.
_TERMINAL_STATUSES = {"completed", "completed_with_errors", "failed"}


@router.post(
    "",
    response_model=ExtractionJobResponse,
    status_code=202,
    summary="Upload document and start extraction",
    description=(
        "Accepts a document upload (PDF, CSV, TXT, MD), saves it to a temporary "
        "location, and creates a pending extraction job. The actual extraction "
        "logic starts when the client connects to the SSE streaming endpoint.\n\n"
        "**Returns 202 Accepted** immediately with a `job_id`."
    ),
)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="The document file to extract data from."),
    schema_id: int = Form(..., description="ID of the ExtractionSchema to use."),
    model: str = Form(
        default="google/gemini-2.0-flash-001",
        description="OpenRouter model string (e.g., 'openai/gpt-4o').",
    ),
    api_key: str | None = Form(
        default=None,
        description="Optional BYOK API key. Bypasses rate limits and whitelist.",
    ),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_demo_access),
) -> ExtractionJobResponse:
    """Accept a document upload, create a pending job, and return immediately.

    The actual extraction runs when the client connects to the SSE stream endpoint.
    """
    # Validate schema exists before writing anything to disk.
    schema = await db.get(ExtractionSchema, schema_id)
    if schema is None:
        raise HTTPException(status_code=404, detail="Schema not found")

    # Write the uploaded file to a temp location the SSE handler can read later.
    suffix = Path(file.filename or "upload").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    job_id = str(uuid.uuid4())
    job = await create_job(
        job_id=job_id,
        schema_id=schema_id,
        original_filename=file.filename or "upload",
        file_type=suffix,
        model=model,
        file_path=tmp_path,
        api_key=api_key,
        db=db,
    )

    return ExtractionJobResponse(
        job_id=job.id,
        status=job.status,
        schema_name=schema.name,
        created_at=job.created_at,
    )


@router.get(
    "/{job_id}/stream",
    summary="Stream extraction progress (SSE)",
    description=(
        "Establishes a Server-Sent Events (SSE) connection to stream LangGraph "
        "node transitions and status updates in real-time.\n\n"
        "Each event is a JSON object matching the `StreamEvent` schema."
    ),
)
async def stream_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Stream LangGraph node progress as Server-Sent Events.

    If the job is already in a terminal state, emit a single 'done' event
    immediately without re-running the graph.
    """
    job: ExtractionJob | None = await db.get(ExtractionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in _TERMINAL_STATUSES:
        # Already finished — emit one synthetic done event.
        async def _already_done():
            done_event = StreamEvent(
                event="done",
                node=None,
                message="Extraction already complete",
                timestamp=datetime.now(tz=UTC),
                data={"status": job.status},
            )
            yield ServerSentEvent(data=done_event.model_dump_json(), event=done_event.event)

        return EventSourceResponse(_already_done())

    async def _generate():
        async for event in stream_extraction(job, db):
            yield ServerSentEvent(data=event.model_dump_json(), event=event.event)

    return EventSourceResponse(_generate())


@router.get(
    "/{job_id}/result",
    response_model=ExtractionResult,
    summary="Get final extraction result",
    description=(
        "Returns the final structured data and processing metadata for a completed job. "
        "Returns 409 Conflict if the job is still processing."
    ),
)
async def get_result(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ExtractionResult:
    """Return the final extraction result for a completed job.

    Returns 409 if the job has not yet reached a terminal state.
    """
    job: ExtractionJob | None = await db.get(ExtractionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Job is not yet complete (status={job.status!r})",
        )
    return ExtractionResult(
        job_id=job.id,
        status=job.status,
        data=job.result_data,
        validation_passed=bool(job.validation_passed),
        retries_used=job.retries_used or 0,
        model_used=job.model_used,
        processing_time_ms=job.processing_time_ms or 0,
        chunks_processed=job.chunks_processed or 0,
    )
