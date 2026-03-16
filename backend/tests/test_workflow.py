"""Tests for the LangGraph extraction workflow."""

from unittest.mock import AsyncMock, MagicMock

from app.workflows.graph import compiled_graph
from app.workflows.state import WorkflowState

INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string"},
        "total_amount": {"type": "number"},
        "line_items": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["invoice_number", "total_amount"],
}


async def test_graph_happy_path(tmp_path, monkeypatch):
    """Graph should complete successfully when LLM returns valid data."""
    doc = tmp_path / "invoice.txt"
    doc.write_text("Invoice #001\nTotal: $100\nItems: widget")

    mock_result = {"invoice_number": "001", "total_amount": 100.0, "line_items": ["widget"]}
    mock_chain = AsyncMock()
    mock_chain.ainvoke = AsyncMock(return_value=mock_result)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    monkeypatch.setattr("app.workflows.nodes.get_llm", lambda **kwargs: mock_llm)

    state = WorkflowState(
        document_id="test-job-1",
        file_path=str(doc),
        schema_definition=INVOICE_SCHEMA,
    )
    result = await compiled_graph.ainvoke(state.model_dump())

    assert result["final_result"] is not None
    assert result["status"] == "completed"
    assert result["retry_count"] == 0


async def test_retry_loop_fires(tmp_path, monkeypatch):
    """Graph should retry extraction when first result fails validation."""
    doc = tmp_path / "invoice.txt"
    doc.write_text("Invoice data")

    # First call returns missing required field, second call returns valid
    invalid_result = {"invoice_number": "001"}  # missing total_amount
    valid_result = {"invoice_number": "001", "total_amount": 99.0}

    call_count = 0

    async def fake_ainvoke(prompt):
        nonlocal call_count
        call_count += 1
        return invalid_result if call_count == 1 else valid_result

    mock_chain = MagicMock()
    mock_chain.ainvoke = fake_ainvoke
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    monkeypatch.setattr("app.workflows.nodes.get_llm", lambda **kwargs: mock_llm)

    state = WorkflowState(
        document_id="test-job-2",
        file_path=str(doc),
        schema_definition=INVOICE_SCHEMA,
    )
    result = await compiled_graph.ainvoke(state.model_dump())

    assert result["retry_count"] == 1
    assert result["status"] == "completed"


async def test_max_retries_graceful(tmp_path, monkeypatch):
    """Graph should complete with errors (not raise) when max retries are exhausted."""
    doc = tmp_path / "invoice.txt"
    doc.write_text("Invoice data")

    # Always returns invalid result (missing total_amount)
    invalid_result = {"invoice_number": "001"}

    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value=invalid_result)
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    monkeypatch.setattr("app.workflows.nodes.get_llm", lambda **kwargs: mock_llm)

    state = WorkflowState(
        document_id="test-job-3",
        file_path=str(doc),
        schema_definition=INVOICE_SCHEMA,
        max_retries=2,  # lower max for faster test
    )
    result = await compiled_graph.ainvoke(state.model_dump())

    # retry_count is incremented in validate_extraction each time validation fails.
    # With max_retries=2:
    #   fail 1 → retry_count=1 (≤2, retry)
    #   fail 2 → retry_count=2 (≤2, retry)
    #   fail 3 → retry_count=3 (>2, route to merge)
    # Final retry_count = max_retries + 1 = 3
    assert result["retry_count"] == result["max_retries"] + 1
    assert result["status"] == "completed_with_errors"
