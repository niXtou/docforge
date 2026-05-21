"""Tests for the LangGraph extraction workflow."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from pytest import MonkeyPatch

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


async def test_graph_happy_path(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
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
    result = await compiled_graph.ainvoke(state)

    assert result["final_result"] is not None
    assert result["status"] == "completed"
    assert result["retry_count"] == 0


async def test_retry_loop_fires(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Graph should retry extraction when first result fails validation."""
    doc = tmp_path / "invoice.txt"
    # Source contains "001" so the grounding check passes via Tier-1 (verbatim)
    # and the shared LLM mock is only consumed by the extract node.
    doc.write_text("Invoice #001 for services rendered")

    # First call returns missing required field, second call returns valid
    invalid_result = {"invoice_number": "001"}  # missing total_amount
    valid_result = {"invoice_number": "001", "total_amount": 99.0}

    call_count = 0

    async def fake_ainvoke(prompt: Any) -> dict[str, Any]:
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
    result = await compiled_graph.ainvoke(state)

    assert result["retry_count"] == 1
    assert result["status"] == "completed"


async def test_llm_error_propagates(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """LLM errors must surface, not be swallowed into an empty result.

    Regression test: a failing ``chain.ainvoke`` used to be caught inside
    ``extract_structured`` and replaced with ``{}``, which downstream looked
    like a successful-but-empty extraction. The retry loop then masked the
    real error as a generic validation failure.
    """
    import pytest

    doc = tmp_path / "invoice.txt"
    doc.write_text("Invoice data")

    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(side_effect=RuntimeError("upstream auth failed"))
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain
    monkeypatch.setattr("app.workflows.nodes.get_llm", lambda **kwargs: mock_llm)

    state = WorkflowState(
        document_id="test-job-err",
        file_path=str(doc),
        schema_definition=INVOICE_SCHEMA,
    )

    with pytest.raises(RuntimeError, match="upstream auth failed"):
        await compiled_graph.ainvoke(state)


async def test_max_retries_graceful(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
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
    result = await compiled_graph.ainvoke(state)

    # retry_count is incremented in validate_extraction each time validation fails.
    # With max_retries=2:
    #   fail 1 → retry_count=1 (≤2, retry)
    #   fail 2 → retry_count=2 (≤2, retry)
    #   fail 3 → retry_count=3 (>2, route to merge)
    # Final retry_count = max_retries + 1 = 3
    assert result["retry_count"] == result["max_retries"] + 1
    assert result["status"] == "completed_with_errors"


RESEARCH_PAPER_SCHEMA = {
    "type": "object",
    "x-doc-type": "research_paper",
    "properties": {
        "title": {"type": "string"},
        "authors": {"type": "array", "items": {"type": "string"}},
        "abstract": {"type": "string"},
    },
    "required": ["title", "authors", "abstract"],
}


async def test_fabricated_author_rejected_then_recovered(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """A fabricated author (absent from the source) is caught by grounding and
    fixed on retry.

    First extraction invents an author not present anywhere in the document.
    verify_grounding finds it is not verbatim-present, the judge rejects it, the
    field is nulled, validation fails (required 'authors' now empty), and the
    retry produces the real byline author — which IS present and passes.
    """
    from app.workflows.nodes import GroundingJudgment

    doc = tmp_path / "paper.txt"
    doc.write_text(
        "Title: Quantum Methods\nBy Jane Doe\nAbstract: We study quantum methods in detail."
    )

    extract_calls = 0

    async def extract_invoke(_messages: Any) -> dict[str, Any]:
        nonlocal extract_calls
        extract_calls += 1
        authors = ["Ghost McFakeName"] if extract_calls == 1 else ["Jane Doe"]
        return {
            "title": "Quantum Methods",
            "authors": authors,
            "abstract": "We study quantum methods in detail.",
        }

    async def judge_invoke(_prompt: Any) -> Any:
        verdict = MagicMock()
        verdict.supported = False  # the fabricated value is unsupported
        verdict.evidence = ""
        return verdict

    extract_chain = MagicMock()
    extract_chain.ainvoke = extract_invoke
    judge_chain = MagicMock()
    judge_chain.ainvoke = judge_invoke

    def route_structured_output(arg: Any) -> MagicMock:
        # The grounding judge binds the GroundingJudgment model; extract binds
        # the user schema dict. Route each to its own mock chain.
        return judge_chain if arg is GroundingJudgment else extract_chain

    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = route_structured_output
    monkeypatch.setattr("app.workflows.nodes.get_llm", lambda **kwargs: mock_llm)

    state = WorkflowState(
        document_id="paper-1",
        file_path=str(doc),
        schema_definition=RESEARCH_PAPER_SCHEMA,
    )
    result = await compiled_graph.ainvoke(state)

    assert result["final_result"]["authors"] == ["Jane Doe"]
    assert result["status"] == "completed"
    assert result["retry_count"] >= 1
