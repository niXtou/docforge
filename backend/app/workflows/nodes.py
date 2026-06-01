"""Individual LangGraph node functions.

Each function in this file is one node in the workflow graph. The contract
for every node is the same:
  - Receives: the current WorkflowState
  - Returns:  a dict containing only the fields it wants to update

LangGraph merges the returned dict into the state automatically. Nodes should
NOT mutate the state object directly — always return a new dict.

NODE EXECUTION ORDER (see graph.py for the wiring):
  parse_document → chunk_text → extract_structured → consolidate
    ↑                                                     │
    │                                                     ▼
    │                                            verify_grounding
    │                                                     │
    └──────── (retry loop) ──── validate_extraction ◄─────┘
                                       │
                                       ▼
                                   finalize
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import pymupdf4llm
from jsonschema import Draft202012Validator
from langchain_community.document_loaders import CSVLoader, TextLoader
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.llm import get_llm
from app.workflows.playbooks import build_system_prompt, strip_extension_keys
from app.workflows.state import WorkflowState

logger = logging.getLogger(__name__)


def _progress_writer() -> Any:
    """Return LangGraph's custom stream writer, or None outside a streaming run.

    Nodes call the returned writer to push fine-grained progress (e.g. "chunk
    3/7") onto the graph's "custom" stream channel. When a node is invoked
    directly (e.g. in unit tests) there is no streaming context, so we fall back
    to None and progress emission becomes a no-op.
    """
    try:
        return get_stream_writer()
    except RuntimeError:
        return None


def _emit(writer: Any, node: str, completed: int, total: int) -> None:
    """Push a progress update onto the custom stream channel, if streaming."""
    if writer is not None:
        writer({"kind": "progress", "node": node, "completed": completed, "total": total})


def _header_signature(line: str) -> str:
    """Normalize a line for header/footer matching.

    Lowercases, collapses whitespace, and replaces digit runs with '#' so that
    per-page numbers like '2 of 11' and '3 of 11' share one signature.
    """
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line)).strip().lower()


def _strip_running_headers(pages: list[str]) -> str:
    """Drop running headers/footers from multi-page PDF text.

    Academic PDFs repeat a running header/footer on every page (e.g.
    'HAYES ET AL.', the journal name, '2 of 11'). The parser keeps these in the
    text, and downstream extraction mistakes them for content — a repeated
    'SURNAME ET AL.' header gets pulled in as an author on every page. We treat
    the top/bottom few lines that recur across many pages as boilerplate and
    remove every line matching those signatures. Short documents (< 3 pages) are
    returned unchanged.
    """
    if len(pages) < 3:
        return "\n\n".join(pages)

    # Only the first/last couple of non-empty lines of a page can be a header
    # or footer. Count how many pages each such signature appears on.
    edge_counts: dict[str, int] = {}
    for page in pages:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        for sig in {_header_signature(ln) for ln in lines[:2] + lines[-2:]}:
            edge_counts[sig] = edge_counts.get(sig, 0) + 1

    # Boilerplate = a short edge signature repeating on at least half the pages.
    threshold = max(3, len(pages) // 2)
    boilerplate = {sig for sig, n in edge_counts.items() if n >= threshold and 0 < len(sig) <= 80}
    if not boilerplate:
        return "\n\n".join(pages)

    cleaned: list[str] = []
    for page in pages:
        kept = [ln for ln in page.splitlines() if _header_signature(ln.strip()) not in boilerplate]
        cleaned.append("\n".join(kept))
    logger.info("Stripped %d running header/footer pattern(s) from PDF", len(boilerplate))
    return "\n\n".join(cleaned)


def _dedupe_preserve_order(items: list[Any]) -> list[Any]:
    """Drop duplicate array values while preserving first-seen order.

    Strings compare case- and whitespace-insensitively (so 'HAYES ET AL.' and
    'Hayes et al.' collapse to one), keeping the first spelling seen. Non-string
    items (e.g. invoice line-item objects) compare by equality.
    """
    seen: list[Any] = []
    out: list[Any] = []
    for item in items:
        key = re.sub(r"\s+", " ", item).strip().lower() if isinstance(item, str) else item
        if key in seen:
            continue
        seen.append(key)
        out.append(item)
    return out


# A bibliographic/citation name form: "Surname AB" — a single surname token
# followed by 1–4 bare initials (e.g. "Hayes CA", "Najmi Z", "Thorpe RJ").
_CITATION_NAME = re.compile(r"^([^\W\d_][\w'’.-]*)\s+(?:[A-Z]\.?){1,4}$")


def _drop_citation_duplicates(items: list[Any]) -> list[Any]:
    """Remove citation-form duplicates of names already listed in fuller form.

    Research papers repeat their own authors in citation style ("Hayes CA") in
    the references and the "How to cite this article" block. The model extracts
    both forms; this drops the abbreviated one *only* when a fuller entry shares
    its surname (so "Hayes CA" is removed because "Cellas A. Hayes" is present,
    but a genuine standalone "Smith J" with no fuller match is kept). Non-string
    items and unrelated arrays (keywords, line items) are unaffected.
    """
    surnames_in_full_form = {
        item.strip().split()[-1].lower()
        for item in items
        if isinstance(item, str) and item.strip() and not _CITATION_NAME.match(item.strip())
    }
    out: list[Any] = []
    for item in items:
        if isinstance(item, str):
            match = _CITATION_NAME.match(item.strip())
            if match and match.group(1).lower() in surnames_in_full_form:
                continue  # abbreviated citation form of an author already present
        out.append(item)
    return out


async def parse_document(state: WorkflowState) -> dict[str, Any]:
    """Load and parse a document from disk into raw text.

    Detects the file type from the extension and dispatches to the
    appropriate LangChain document loader.
    """
    ext = state.file_type if state.file_type else Path(state.file_path).suffix.lower()

    if ext == ".pdf":
        # pymupdf4llm produces clean markdown — preserves word order in styled fonts.
        # page_chunks=True returns one dict per page (keyed "text"), which lets us
        # detect and strip running headers/footers before they pollute extraction.
        try:
            page_dicts: Any = await asyncio.to_thread(
                pymupdf4llm.to_markdown, state.file_path, page_chunks=True
            )
        except Exception as e:
            raise FileNotFoundError(f"Could not read file {state.file_path}: {e}") from e
        pages = [str(p.get("text", "")) for p in page_dicts]
        text = _strip_running_headers(pages)
        logger.info("Parsed PDF document (%d page(s)) from %s", len(pages), state.file_path)
        return {
            "raw_content": text,
            "file_type": ext,
            "messages": state.messages + [f"Parsed PDF document ({len(pages)} page(s))"],
        }

    if ext == ".csv":
        loader: CSVLoader | TextLoader = CSVLoader(state.file_path)
    elif ext in {".txt", ".md"}:
        loader = TextLoader(state.file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    try:
        docs = await asyncio.to_thread(loader.load)
    except OSError as e:
        raise FileNotFoundError(f"Could not read file {state.file_path}: {e}") from e

    text = "\n\n".join(doc.page_content for doc in docs)

    logger.info("Parsed %d document(s) from %s file", len(docs), ext)
    return {
        "raw_content": text,
        "file_type": ext,
        "messages": state.messages + [f"Parsed {len(docs)} document(s) from {ext} file"],
    }


async def chunk_text(state: WorkflowState) -> dict[str, Any]:
    """Split raw content into chunks suitable for LLM processing.

    Documents at or below ``settings.single_pass_char_limit`` are kept as a
    single chunk and extracted in one LLM call — modern large-context models
    handle this comfortably, and a single pass sidesteps the merge-reconciliation
    errors that arise when the same field is extracted across several chunks.

    Larger documents are split with overlap to preserve context across chunk
    boundaries. Chunk 0 is the *primary* chunk: header/scalar fields (names,
    titles, authors) live at the top of a document, so the consolidate step
    sources scalars from it rather than letting a later chunk overwrite them.
    """
    if len(state.raw_content) <= settings.single_pass_char_limit:
        # Short document — send it all in one LLM call, no merge needed.
        return {"chunks": [state.raw_content], "primary_chunk_index": 0}

    # RecursiveCharacterTextSplitter tries to split on paragraph breaks first,
    # then sentences, then words — preferring natural boundaries over hard cuts.
    # chunk_overlap means consecutive chunks share context so a field that spans
    # a boundary isn't lost.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    chunks = splitter.split_text(state.raw_content)
    logger.info("Split document into %d chunks", len(chunks))
    return {"chunks": chunks, "primary_chunk_index": 0}


async def extract_structured(state: WorkflowState) -> dict[str, Any]:
    """Run structured extraction on each chunk using the configured LLM.

    Builds a prompt per chunk and invokes the LLM with structured-output
    mode so the response already conforms to the user-supplied JSON Schema.
    On retries the previous validation errors are prepended to the prompt
    so the LLM knows what it got wrong and can try to fix it.

    WHAT IS STRUCTURED OUTPUT?
    ───────────────────────────
    `llm.with_structured_output(schema)` tells the LLM to respond with JSON
    that matches the given JSON Schema, instead of free-form text. LangChain
    handles the prompt engineering and response parsing for this automatically.
    """
    llm = get_llm(model=state.model, api_key=state.api_key)

    # The schema's x-doc-type selects the disambiguation playbook (e.g. "authors
    # are the byline, not the references"). The system prompt = universal
    # anti-hallucination rules + that playbook. This is the knowledge that the
    # UI's schema selection used to carry but never reached the model.
    doc_type = state.schema_definition.get("x-doc-type")
    system_prompt = build_system_prompt(doc_type)

    # Strip x-* extension keys before structured output — they are our metadata,
    # not valid input for the model API. Add a title for the function name.
    schema = strip_extension_keys(state.schema_definition)
    if "title" not in schema:
        schema = {"title": "ExtractionResult", **schema}
    chain = llm.with_structured_output(schema)

    # Extract every chunk concurrently (bounded) instead of one-at-a-time. A
    # multi-chunk document used to make N sequential LLM calls with no feedback,
    # which looked frozen and ran N× slower than necessary. asyncio.gather
    # preserves input order, so chunk 0 stays the primary chunk for consolidate.
    writer = _progress_writer()
    total = len(state.chunks)
    semaphore = asyncio.Semaphore(settings.extract_concurrency)
    completed = 0
    counter_lock = asyncio.Lock()

    async def _extract_chunk(chunk: str) -> dict[str, Any]:
        nonlocal completed
        user_sections = [
            "Extract data into this schema. Each field's 'description' is the "
            f"authoritative instruction for what to extract:\n{json.dumps(schema)}",
            f"Document content:\n{chunk}",
        ]
        if state.retry_count > 0:
            # On a retry, lead with the previous problems so the model self-corrects.
            user_sections.insert(
                0,
                "Your previous attempt had these problems — fix them:\n"
                + "\n".join(state.last_validation_errors),
            )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content="\n\n".join(user_sections)),
        ]

        # Let LLM exceptions propagate. The previous version swallowed them
        # and returned ``{}``, which the validator mistook for "missing
        # required fields" — turning auth or model errors into misleading
        # validation failures. ``_run_extraction_task`` already catches the
        # raised exception, marks the job as ``failed``, persists the error
        # to ``error_message`` and emits an SSE ``error`` event.
        async with semaphore:
            result = await chain.ainvoke(messages)

        # Normalise to plain dict regardless of what the LLM client returned
        if isinstance(result, dict):
            result_dict: dict[str, Any] = result
        else:
            # Pydantic model or other structured output
            try:
                result_dict = result.model_dump()  # type: ignore[union-attr]
            except AttributeError:
                result_dict = dict(result)  # type: ignore[call-overload]

        async with counter_lock:
            completed += 1
            _emit(writer, "extract", completed, total)
        logger.debug("Extracted chunk result: %s", list(result_dict.keys()))
        return result_dict

    results = list(await asyncio.gather(*(_extract_chunk(c) for c in state.chunks)))
    return {"chunk_extractions": results}


def _is_empty(value: Any) -> bool:
    """True if a value should be treated as 'not extracted' (None / blank / [])."""
    return value is None or value == "" or value == []


def _merge_chunks(
    chunk_extractions: list[dict[str, Any]],
    properties: dict[str, Any],
    primary_index: int = 0,
) -> dict[str, Any]:
    """Merge per-chunk extraction dicts respecting array vs scalar field types.

    Merge strategy:
      - Array fields  (schema type = "array"):  concatenate all chunk values
        in chunk order (e.g. line items in an invoice, skills on a CV).
      - Scalar fields (everything else):        take the PRIMARY chunk's value.
        Header/scalar fields (name, title, author) live at the top of a
        document, so the primary chunk (index 0) is authoritative. Only if the
        primary chunk did not extract the field do we fall back to the first
        other chunk that did. This replaces the old "last chunk wins", which
        let a later chunk's guess overwrite a correct early value.

    Pure helper, no side effects.
    """
    merged: dict[str, Any] = {}
    # Order chunks so the primary chunk is considered first for scalar fallback.
    ordered = list(chunk_extractions)
    if 0 <= primary_index < len(ordered):
        primary = ordered.pop(primary_index)
        ordered.insert(0, primary)

    for extraction in ordered:
        for field, value in extraction.items():
            if properties.get(field, {}).get("type") == "array":
                existing = merged.get(field, [])
                if isinstance(existing, list) and isinstance(value, list):
                    # Concatenate across chunks, then drop duplicates: the same
                    # value (e.g. a repeated header the model mistook for content)
                    # is often emitted by several chunks.
                    merged[field] = _dedupe_preserve_order(existing + value)
                else:
                    merged[field] = value
            else:
                # Scalar: first non-empty value in primary-first order wins.
                if _is_empty(merged.get(field)) and not _is_empty(value) or field not in merged:
                    merged[field] = value
    return merged


async def consolidate(state: WorkflowState) -> dict[str, Any]:
    """Merge per-chunk extractions into one working dict (``consolidated``).

    Runs after extraction and before grounding/validation. Arrays accumulate
    across chunks; scalars come from the primary chunk. For single-pass
    documents (one chunk) this is a trivial pass-through.
    """
    properties: dict[str, Any] = state.schema_definition.get("properties", {})
    merged = _merge_chunks(state.chunk_extractions, properties, state.primary_chunk_index)

    # Drop citation-form duplicates (e.g. "Hayes CA" when "Cellas A. Hayes" is
    # already present) from array fields — papers self-cite their own authors.
    for field, spec in properties.items():
        if spec.get("type") == "array" and isinstance(merged.get(field), list):
            merged[field] = _drop_citation_duplicates(merged[field])

    logger.info(
        "Consolidated %d chunk(s) into %d field(s)", len(state.chunk_extractions), len(merged)
    )
    return {"consolidated": merged}


class GroundingJudgment(BaseModel):
    """Structured verdict from the LLM grounding judge for one value."""

    supported: bool = Field(description="True if the value is supported by the document text")
    evidence: str = Field(description="A short quote from the document that supports it, or empty")


def _normalize(text: str) -> str:
    """Lowercase and collapse all whitespace runs to single spaces for matching."""
    return re.sub(r"\s+", " ", text).strip().lower()


async def _judge(llm_chain: Any, field: str, value: str, source: str) -> GroundingJudgment:
    """Ask the LLM whether ``value`` for ``field`` is supported by ``source``."""
    prompt = (
        f"Document:\n{source}\n\n"
        f"A system extracted the value below for the field '{field}'. Decide whether the "
        f"document actually supports this exact value. Answer supported=false if it was "
        f"inferred, guessed, or taken from an unrelated part of the document (e.g. a cited "
        f"author rather than the document's own author).\n\n"
        f"Value: {value}"
    )
    return await llm_chain.ainvoke(prompt)


async def verify_grounding(state: WorkflowState) -> dict[str, Any]:
    """Check that each extracted string value is actually supported by the source.

    Two tiers, cheapest first:
      1. Verbatim presence — if the normalized value appears in the normalized
         source text, it is grounded for free (no LLM call).
      2. LLM judge — values not found verbatim are sent to the model, which
         decides whether the document supports them (catching, e.g., a cited
         author mistaken for the byline). Rejected values are nulled out and an
         issue is recorded.

    Only string scalars and string array items are checked — numbers/dates are
    frequently reformatted, so verbatim matching is unreliable for them and they
    are left to schema validation instead. Grounding issues are written to
    ``grounding_issues``; validate folds them into the retry feedback.
    """
    consolidated: dict[str, Any] = dict(state.consolidated or {})
    source_norm = _normalize(state.raw_content)
    issues: list[str] = []

    # Collect string values that are NOT present verbatim — only these need a judge.
    to_judge: list[tuple[str, str, int | None]] = []  # (field, value, list_index or None)
    for field, value in consolidated.items():
        if isinstance(value, str) and value.strip():
            if _normalize(value) not in source_norm:
                to_judge.append((field, value, None))
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, str) and item.strip() and _normalize(item) not in source_norm:
                    to_judge.append((field, item, idx))

    if not to_judge:
        return {"consolidated": consolidated, "grounding_issues": []}

    llm = get_llm(model=state.model, api_key=state.api_key)
    judge_chain = llm.with_structured_output(GroundingJudgment)

    # Judge all flagged values concurrently (bounded). Verdicts are applied
    # afterwards in the original order so issue ordering stays deterministic.
    writer = _progress_writer()
    total = len(to_judge)
    semaphore = asyncio.Semaphore(settings.extract_concurrency)
    completed = 0
    counter_lock = asyncio.Lock()

    async def _judge_one(field: str, value: str) -> GroundingJudgment:
        nonlocal completed
        async with semaphore:
            verdict = await _judge(judge_chain, field, value, state.raw_content)
        async with counter_lock:
            completed += 1
            _emit(writer, "verify_grounding", completed, total)
        return verdict

    verdicts = await asyncio.gather(*(_judge_one(f, v) for f, v, _ in to_judge))

    # Track array items to drop after iterating (don't mutate lists mid-loop).
    drop_items: dict[str, set[int]] = {}
    for (field, value, list_index), verdict in zip(to_judge, verdicts, strict=True):
        if not getattr(verdict, "supported", False):
            issues.append(f"Field '{field}': value '{value}' is not supported by the document")
            if list_index is None:
                consolidated[field] = None
            else:
                drop_items.setdefault(field, set()).add(list_index)

    for field, indices in drop_items.items():
        consolidated[field] = [
            item for i, item in enumerate(consolidated[field]) if i not in indices
        ]

    if issues:
        logger.warning("Grounding rejected %d value(s)", len(issues))
    return {"consolidated": consolidated, "grounding_issues": issues}


async def validate_extraction(state: WorkflowState) -> dict[str, Any]:
    """Validate the consolidated result against the schema, three ways.

    Operates on ``state.consolidated`` (produced by consolidate, refined by
    verify_grounding) and accumulates three classes of error:
      1. Grounding issues carried over from verify_grounding.
      2. Required fields that are missing or empty.
      3. JSON-Schema violations on the present values (wrong type, bad enum,
         failed format) — caught via ``jsonschema``. This is what lets the
         retry loop fix *wrong* values, not just *missing* ones.

    Empty/None values are dropped before type-checking so a field that wasn't
    extracted reads as "missing required" rather than a spurious type error.

    NOTE: retry_count is incremented HERE (in validate), not in extract.
    The router reads retry_count immediately after validate returns; bumping it
    in extract would mis-count the first (non-retry) attempt.
    """
    consolidated: dict[str, Any] = state.consolidated or {}
    schema = strip_extension_keys(state.schema_definition)
    errors: list[str] = list(state.grounding_issues)

    # 2. Required-present (treat None / "" / [] as missing).
    for field in schema.get("required", []):
        if _is_empty(consolidated.get(field)):
            errors.append(f"Required field '{field}' is missing or empty")

    # 3. JSON-Schema type/enum/format checks on the values that ARE present.
    #    'required' is handled above, so validate a copy without it to avoid
    #    double-reporting missing fields.
    type_schema = {k: v for k, v in schema.items() if k != "required"}
    instance = {k: v for k, v in consolidated.items() if not _is_empty(v)}
    for err in Draft202012Validator(type_schema).iter_errors(instance):
        location = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"Field '{location}': {err.message}")

    if errors:
        logger.warning("Validation failed with %d error(s)", len(errors))
        return {"last_validation_errors": errors, "retry_count": state.retry_count + 1}

    logger.info("Validation passed")
    return {"last_validation_errors": [], "retry_count": state.retry_count}


async def finalize(state: WorkflowState) -> dict[str, Any]:
    """Promote the consolidated+verified working result to the final output.

    The heavy lifting (merging, grounding, validation) already happened upstream;
    this node just publishes ``consolidated`` as ``final_result`` and sets the
    terminal status. ``completed_with_errors`` means we exhausted retries but
    still produced a best-effort result.
    """
    status = "completed" if not state.last_validation_errors else "completed_with_errors"
    logger.info("Finalize complete — status: %s", status)
    return {"final_result": state.consolidated or {}, "status": status}
