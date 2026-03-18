"""Stage 3 tests: schema CRUD and extraction endpoints."""

import io
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import seed_builtin_schemas
from app.models.db import ExtractionJob, ExtractionSchema

# ── Schema endpoint tests ─────────────────────────────────────────────────────


async def test_list_schemas_empty(client: AsyncClient) -> None:
    """GET /api/schemas returns an empty list when no schemas exist."""
    response = await client.get("/api/schemas")
    assert response.status_code == 200
    assert response.json() == []


async def test_create_schema_returns_201(client: AsyncClient) -> None:
    """POST /api/schemas creates a schema and returns 201 with the new object."""
    payload = {
        "name": "Invoice Test",
        "description": "Test invoice schema",
        "json_schema": {
            "type": "object",
            "properties": {"invoice_number": {"type": "string"}},
            "required": ["invoice_number"],
        },
    }
    response = await client.post("/api/schemas", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Invoice Test"
    assert body["is_builtin"] is False
    assert "id" in body


async def test_get_schema_by_id(client: AsyncClient, seeded_schema: ExtractionSchema) -> None:
    """GET /api/schemas/{id} returns the correct schema."""
    response = await client.get(f"/api/schemas/{seeded_schema.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == seeded_schema.id
    assert body["name"] == seeded_schema.name


async def test_get_schema_404(client: AsyncClient) -> None:
    """GET /api/schemas/{id} returns 404 for an unknown schema ID."""
    response = await client.get("/api/schemas/99999")
    assert response.status_code == 404


async def test_create_schema_duplicate_409(client: AsyncClient) -> None:
    """POST /api/schemas returns 409 when the schema name already exists."""
    payload = {
        "name": "Duplicate Schema",
        "description": "",
        "json_schema": {"type": "object", "properties": {}},
    }
    first = await client.post("/api/schemas", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/schemas", json=payload)
    assert second.status_code == 409


async def test_builtin_schema_seeding(db_session: AsyncSession) -> None:
    """seed_builtin_schemas inserts the 3 built-in schemas exactly once."""
    await seed_builtin_schemas(db_session)
    # Calling a second time should be idempotent (no duplicate inserts).
    await seed_builtin_schemas(db_session)

    from sqlalchemy import select

    result = await db_session.execute(
        select(ExtractionSchema).where(ExtractionSchema.is_builtin.is_(True))
    )
    builtins = result.scalars().all()
    assert len(builtins) == 3
    names = {s.name for s in builtins}
    assert "Invoice" in names
    assert "Resume/CV" in names
    assert "Research Paper" in names


# ── Extraction endpoint tests ─────────────────────────────────────────────────


async def test_upload_creates_pending_job(
    client: AsyncClient, seeded_schema: ExtractionSchema
) -> None:
    """POST /api/extract returns 202 with status='pending' (rate limit bypassed)."""
    from app.core.security import require_demo_access
    from app.main import app

    async def _bypass() -> None:
        return None

    app.dependency_overrides[require_demo_access] = _bypass
    try:
        response = await client.post(
            "/api/extract",
            data={"schema_id": str(seeded_schema.id), "model": "google/gemini-2.0-flash"},
            files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
        )
    finally:
        app.dependency_overrides.pop(require_demo_access, None)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert "job_id" in body


async def test_upload_model_not_allowed(
    client: AsyncClient, seeded_schema: ExtractionSchema
) -> None:
    """POST /api/extract returns 403 when a non-whitelisted model is used without api_key."""
    response = await client.post(
        "/api/extract",
        data={
            "schema_id": str(seeded_schema.id),
            "model": "openai/gpt-4-turbo",  # not in demo_allowed_models
        },
        files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["detail"]["code"] == "model_not_allowed"


async def test_upload_rate_limit_exceeded(
    client: AsyncClient, seeded_schema: ExtractionSchema
) -> None:
    """POST /api/extract returns 429 when the Redis rate counter exceeds the limit."""
    mock_redis = MagicMock()
    mock_redis.incr = AsyncMock(return_value=9999)
    mock_redis.expire = AsyncMock()

    async def _mock_get_redis():
        return mock_redis

    with patch("app.core.security.get_redis", new=_mock_get_redis):
        response = await client.post(
            "/api/extract",
            data={
                "schema_id": str(seeded_schema.id),
                "model": "google/gemini-2.0-flash",
            },
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        )
    assert response.status_code == 429
    body = response.json()
    assert body["detail"]["code"] == "rate_limit_exceeded"


async def test_upload_byok_bypasses_whitelist(
    client: AsyncClient, seeded_schema: ExtractionSchema
) -> None:
    """POST /api/extract with api_key allows any model and skips rate limiting."""
    # No Redis mock needed: BYOK skips the rate-limit check entirely.
    response = await client.post(
        "/api/extract",
        data={
            "schema_id": str(seeded_schema.id),
            "model": "openai/gpt-4-turbo",  # not in demo_allowed_models
            "api_key": "sk-test-key",
        },
        files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"


async def test_stream_emits_node_events(
    client: AsyncClient, seeded_schema: ExtractionSchema, db_session: AsyncSession
) -> None:
    """GET /api/extract/{job_id}/stream emits node_completed and done SSE events."""
    # Create a pending job in the DB directly.
    job_id = str(uuid.uuid4())
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(b"test content")
        tmp_path = f.name

    job = ExtractionJob(
        id=job_id,
        schema_id=seeded_schema.id,
        status="pending",
        original_filename="test.txt",
        file_type=".txt",
        model_used="google/gemini-2.0-flash",
        file_path=tmp_path,
        api_key=None,
    )
    db_session.add(job)
    await db_session.commit()

    # Monkeypatch compiled_graph.astream to return fake node updates.
    fake_node_output = {"parse": {"file_path": tmp_path, "chunks": ["chunk1"]}}

    async def _fake_astream(state: object):  # type: ignore[override]
        yield fake_node_output

    with patch("app.services.extraction.compiled_graph") as mock_graph:
        mock_graph.astream = _fake_astream
        response = await client.get(f"/api/extract/{job_id}/stream")

    assert response.status_code == 200
    body = response.text
    assert "node_completed" in body
    assert "done" in body


async def test_stream_already_done_job(
    client: AsyncClient, seeded_schema: ExtractionSchema, db_session: AsyncSession
) -> None:
    """GET /api/extract/{job_id}/stream emits a single done event for a completed job."""
    job_id = str(uuid.uuid4())
    job = ExtractionJob(
        id=job_id,
        schema_id=seeded_schema.id,
        status="completed",
        original_filename="done.txt",
        file_type=".txt",
        model_used="google/gemini-2.0-flash",
        result_data={"field1": "value1"},
        validation_passed=True,
        completed_at=datetime.now(tz=UTC),
    )
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/api/extract/{job_id}/stream")
    assert response.status_code == 200
    assert "done" in response.text


async def test_result_completed_job(
    client: AsyncClient, seeded_schema: ExtractionSchema, db_session: AsyncSession
) -> None:
    """GET /api/extract/{job_id}/result returns 200 ExtractionResult for a completed job."""
    job_id = str(uuid.uuid4())
    job = ExtractionJob(
        id=job_id,
        schema_id=seeded_schema.id,
        status="completed",
        original_filename="done.txt",
        file_type=".txt",
        model_used="google/gemini-2.0-flash",
        result_data={"field1": "extracted_value"},
        validation_passed=True,
        processing_time_ms=1234,
        chunks_processed=2,
        completed_at=datetime.now(tz=UTC),
    )
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/api/extract/{job_id}/result")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["status"] == "completed"
    assert body["data"] == {"field1": "extracted_value"}
    assert body["validation_passed"] is True


async def test_result_pending_job_409(
    client: AsyncClient, seeded_schema: ExtractionSchema, db_session: AsyncSession
) -> None:
    """GET /api/extract/{job_id}/result returns 409 when the job is still pending."""
    job_id = str(uuid.uuid4())
    job = ExtractionJob(
        id=job_id,
        schema_id=seeded_schema.id,
        status="pending",
        original_filename="pending.txt",
        file_type=".txt",
        model_used="google/gemini-2.0-flash",
    )
    db_session.add(job)
    await db_session.commit()

    response = await client.get(f"/api/extract/{job_id}/result")
    assert response.status_code == 409


async def test_result_not_found_404(client: AsyncClient) -> None:
    """GET /api/extract/{job_id}/result returns 404 for an unknown job ID."""
    response = await client.get(f"/api/extract/{uuid.uuid4()}/result")
    assert response.status_code == 404
