"""Tests for doc-type playbooks and JSON-Schema extension-key handling."""

from app.workflows.playbooks import build_system_prompt, strip_extension_keys


def test_base_rules_present_for_every_prompt() -> None:
    """The anti-hallucination base rule must appear regardless of doc type."""
    prompt = build_system_prompt("research_paper")
    lowered = prompt.lower()
    assert "null" in lowered  # "return null if not present"
    assert "not infer" in lowered or "never infer" in lowered or "do not infer" in lowered


def test_research_paper_playbook_disambiguates_authors() -> None:
    """Research-paper playbook must tell the model authors != references."""
    prompt = build_system_prompt("research_paper").lower()
    assert "author" in prompt
    assert "reference" in prompt or "citation" in prompt


def test_research_paper_playbook_includes_group_authors() -> None:
    """Byline group / consortium authors (e.g. 'X Study Team') must be captured."""
    prompt = build_system_prompt("research_paper").lower()
    assert "group" in prompt or "consortium" in prompt


def test_unknown_doc_type_falls_back_to_generic() -> None:
    """An unrecognised doc type must not raise — it falls back to generic."""
    prompt = build_system_prompt("totally_unknown_type")
    assert isinstance(prompt, str)
    assert prompt.strip()  # non-empty


def test_none_doc_type_uses_generic() -> None:
    """No doc type (custom user schema) still yields the base/generic prompt."""
    prompt = build_system_prompt(None)
    assert "null" in prompt.lower()


def test_strip_extension_keys_removes_x_prefixed_top_level_keys() -> None:
    """x-* keys are stripped so they are not sent to with_structured_output."""
    schema = {
        "type": "object",
        "x-doc-type": "research_paper",
        "properties": {"authors": {"type": "array"}},
        "required": ["authors"],
    }
    cleaned = strip_extension_keys(schema)
    assert "x-doc-type" not in cleaned
    assert cleaned["properties"] == {"authors": {"type": "array"}}
    assert cleaned["required"] == ["authors"]


def test_strip_extension_keys_does_not_mutate_input() -> None:
    """Stripping returns a new dict; the caller's schema is untouched."""
    schema = {"type": "object", "x-doc-type": "invoice"}
    strip_extension_keys(schema)
    assert "x-doc-type" in schema  # original still has it
