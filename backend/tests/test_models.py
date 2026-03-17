"""Tests for Pydantic model validation."""

import pytest
from pydantic import ValidationError

from app.models.schemas import ExtractionRequest
from app.workflows.state import WorkflowState


def test_extraction_request_schema_id_must_be_positive():
    with pytest.raises(ValidationError):
        ExtractionRequest(schema_id=0)
    with pytest.raises(ValidationError):
        ExtractionRequest(schema_id=-1)


def test_extraction_request_model_cannot_be_empty():
    with pytest.raises(ValidationError):
        ExtractionRequest(schema_id=1, model="")


def test_workflow_state_defaults():
    state = WorkflowState(
        document_id="test",
        schema_definition={"type": "object"},
    )
    assert state.status == "pending"
    assert state.retry_count == 0
    assert state.max_retries == 3
    assert state.chunks == []
    assert state.final_result is None
    assert state.model == "google/gemini-2.0-flash"
