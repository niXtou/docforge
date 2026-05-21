"""Unit tests for individual workflow nodes (chunk, consolidate, verify, validate)."""

from unittest.mock import AsyncMock, MagicMock

from pytest import MonkeyPatch

from app.core.config import settings
from app.workflows.nodes import (
    chunk_text,
    consolidate,
    extract_structured,
    validate_extraction,
    verify_grounding,
)
from app.workflows.state import WorkflowState

NUMERIC_SCHEMA = {
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string"},
        "total_amount": {"type": "number"},
    },
    "required": ["invoice_number", "total_amount"],
}

CV_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["full_name"],
}


def _state(**kwargs: object) -> WorkflowState:
    """Build a minimal WorkflowState for node-level tests."""
    base: dict[str, object] = {
        "document_id": "t",
        "schema_definition": {"type": "object", "properties": {}},
    }
    base.update(kwargs)
    return WorkflowState(**base)  # type: ignore[arg-type]


async def test_chunk_single_pass_below_threshold(monkeypatch: MonkeyPatch) -> None:
    """A document under the single-pass limit becomes exactly one chunk."""
    monkeypatch.setattr(settings, "single_pass_char_limit", 1000)
    state = _state(raw_content="short document")
    result = await chunk_text(state)
    assert result["chunks"] == ["short document"]


async def test_chunk_splits_above_threshold(monkeypatch: MonkeyPatch) -> None:
    """A document over the single-pass limit is split into multiple chunks."""
    monkeypatch.setattr(settings, "single_pass_char_limit", 50)
    monkeypatch.setattr(settings, "chunk_size", 50)
    monkeypatch.setattr(settings, "chunk_overlap", 10)
    # 600 chars of varied content forces RecursiveCharacterTextSplitter to split.
    big = "\n\n".join(f"Paragraph {i} with some words here." for i in range(20))
    state = _state(raw_content=big)
    result = await chunk_text(state)
    assert len(result["chunks"]) > 1


async def test_consolidate_scalar_from_primary_not_last_chunk() -> None:
    """Scalar fields come from the primary chunk, not the last one.

    Regression for the 'last-chunk-wins' bug: a correct name in chunk 0 used to
    be overwritten by a later chunk's guess.
    """
    state = _state(
        schema_definition=CV_SCHEMA,
        chunk_extractions=[
            {"full_name": "Alice Real", "skills": ["python"]},
            {"full_name": "Bob Cited", "skills": ["go"]},
        ],
        primary_chunk_index=0,
    )
    result = await consolidate(state)
    merged = result["consolidated"]
    assert merged["full_name"] == "Alice Real"  # primary chunk wins, not "Bob Cited"
    assert merged["skills"] == ["python", "go"]  # arrays accumulate across chunks


async def test_consolidate_scalar_falls_back_when_primary_missing() -> None:
    """If the primary chunk lacks a scalar, fall back to the first chunk that has it."""
    state = _state(
        schema_definition=CV_SCHEMA,
        chunk_extractions=[
            {"skills": ["python"]},  # primary chunk has no name
            {"full_name": "Bob Found", "skills": ["go"]},
        ],
        primary_chunk_index=0,
    )
    result = await consolidate(state)
    assert result["consolidated"]["full_name"] == "Bob Found"


def _mock_get_llm(monkeypatch: MonkeyPatch, supported: bool) -> MagicMock:
    """Patch get_llm so the grounding judge returns a fixed verdict."""
    judgment = MagicMock()
    judgment.supported = supported
    judgment.evidence = "" if not supported else "found"
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=judgment)
    llm = MagicMock()
    llm.with_structured_output.return_value = chain
    monkeypatch.setattr("app.workflows.nodes.get_llm", lambda **kwargs: llm)
    return chain


async def test_grounding_nulls_value_judge_rejects(monkeypatch: MonkeyPatch) -> None:
    """A value absent from the source and rejected by the judge is nulled out."""
    chain = _mock_get_llm(monkeypatch, supported=False)
    state = _state(
        schema_definition=CV_SCHEMA,
        raw_content="Resume of Alice Real. Skills: Python.",
        consolidated={"full_name": "Ghost Author", "skills": ["Python"]},
    )
    result = await verify_grounding(state)
    assert result["consolidated"]["full_name"] is None  # hallucinated name removed
    assert result["grounding_issues"]  # an issue was recorded
    chain.ainvoke.assert_awaited()  # judge was consulted for the absent value


async def test_grounding_tier1_verbatim_skips_judge(monkeypatch: MonkeyPatch) -> None:
    """A value present verbatim in the source is grounded for free — no judge call."""
    chain = _mock_get_llm(monkeypatch, supported=False)
    state = _state(
        schema_definition=CV_SCHEMA,
        raw_content="Resume of Alice Real. Skills: Python.",
        consolidated={"full_name": "Alice Real", "skills": ["Python"]},
    )
    result = await verify_grounding(state)
    assert result["consolidated"]["full_name"] == "Alice Real"  # kept
    assert not result["grounding_issues"]
    chain.ainvoke.assert_not_awaited()  # Tier-1 hit: judge never called


async def test_validate_catches_type_mismatch() -> None:
    """A value of the wrong JSON type is flagged (not just missing required fields)."""
    state = _state(
        schema_definition=NUMERIC_SCHEMA,
        consolidated={"invoice_number": "001", "total_amount": "lots of money"},
    )
    result = await validate_extraction(state)
    assert result["retry_count"] == 1
    assert any("total_amount" in e for e in result["last_validation_errors"])


async def test_validate_passes_clean_result() -> None:
    """A schema-valid result yields no errors and does not bump retry_count."""
    state = _state(
        schema_definition=NUMERIC_SCHEMA,
        consolidated={"invoice_number": "001", "total_amount": 99.0},
    )
    result = await validate_extraction(state)
    assert result["last_validation_errors"] == []
    assert result["retry_count"] == 0


async def test_validate_folds_in_grounding_issues() -> None:
    """Grounding issues from verify_grounding flow into the retry feedback."""
    state = _state(
        schema_definition=NUMERIC_SCHEMA,
        consolidated={"invoice_number": "001", "total_amount": 99.0},
        grounding_issues=["Field 'invoice_number': value '001' is not supported"],
    )
    result = await validate_extraction(state)
    assert any("not supported" in e for e in result["last_validation_errors"])
    assert result["retry_count"] == 1


async def test_extract_injects_playbook_and_strips_extension_keys(
    monkeypatch: MonkeyPatch,
) -> None:
    """Extract sends a doc-type system prompt and strips x-* keys from the schema."""
    captured: dict[str, object] = {}

    async def fake_ainvoke(messages: object) -> dict[str, object]:
        captured["messages"] = messages
        return {"authors": ["Real Author"]}

    chain = MagicMock()
    chain.ainvoke = fake_ainvoke
    llm = MagicMock()

    def capture_schema(schema: dict[str, object]) -> MagicMock:
        captured["schema"] = schema
        return chain

    llm.with_structured_output.side_effect = capture_schema
    monkeypatch.setattr("app.workflows.nodes.get_llm", lambda **kwargs: llm)

    schema = {
        "type": "object",
        "x-doc-type": "research_paper",
        "properties": {"authors": {"type": "array", "items": {"type": "string"}}},
        "required": ["authors"],
    }
    state = _state(schema_definition=schema, chunks=["A paper by Real Author."])
    await extract_structured(state)

    # x-doc-type must not reach the model API.
    assert "x-doc-type" not in captured["schema"]  # type: ignore[operator]
    # The research-paper playbook (authors vs references) must be in the prompt.
    prompt_text = str(captured["messages"]).lower()
    assert "author" in prompt_text
    assert "reference" in prompt_text or "citation" in prompt_text
