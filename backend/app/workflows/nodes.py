"""Individual LangGraph node functions.

Each function in this file is one node in the workflow graph. The contract
for every node is the same:
  - Receives: the current WorkflowState
  - Returns:  a dict containing only the fields it wants to update

LangGraph merges the returned dict into the state automatically. Nodes should
NOT mutate the state object directly — always return a new dict.

NODE EXECUTION ORDER (see graph.py for the wiring):
  parse_document → chunk_text → extract_structured → validate_extraction
    ↑                                                        │
    └────────────────────── (retry loop) ────────────────────┘
                                                             ↓
                                                    merge_extractions
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from langchain_community.document_loaders import CSVLoader, PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.llm import get_llm
from app.workflows.state import WorkflowState

logger = logging.getLogger(__name__)


async def parse_document(state: WorkflowState) -> dict[str, Any]:
    """Load and parse a document from disk into raw text.

    Detects the file type from the extension and dispatches to the
    appropriate LangChain document loader.
    """
    ext = state.file_type if state.file_type else Path(state.file_path).suffix.lower()

    if ext == ".pdf":
        loader: PyPDFLoader | CSVLoader | TextLoader = PyPDFLoader(state.file_path)
    elif ext == ".csv":
        loader = CSVLoader(state.file_path)
    elif ext in {".txt", ".md"}:
        loader = TextLoader(state.file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    # LangChain loaders are synchronous. We run them in a thread so they don't
    # block the async event loop while reading from disk.
    try:
        docs = await asyncio.to_thread(loader.load)
    except OSError as e:
        raise FileNotFoundError(f"Could not read file {state.file_path}: {e}") from e

    # Multi-page documents (PDFs) produce one `Document` object per page.
    # We join them into a single string for uniform downstream processing.
    text = "\n\n".join(doc.page_content for doc in docs)

    logger.info("Parsed %d document(s) from %s file", len(docs), ext)
    return {
        "raw_content": text,
        "file_type": ext,
        "messages": state.messages + [f"Parsed {len(docs)} document(s) from {ext} file"],
    }


async def chunk_text(state: WorkflowState) -> dict[str, Any]:
    """Split raw content into chunks suitable for LLM processing.

    Documents under 4 000 characters are kept as a single chunk.
    Larger documents are split with overlap to preserve context across
    chunk boundaries.
    """
    if len(state.raw_content) <= 4000:
        # Short document — no need to split, send it all in one LLM call
        return {"chunks": [state.raw_content]}

    # RecursiveCharacterTextSplitter tries to split on paragraph breaks first,
    # then sentences, then words — preferring natural boundaries over hard cuts.
    # chunk_overlap=400 means consecutive chunks share 400 chars of context so
    # a field that spans a boundary isn't lost.
    # TODO: make chunk_size and chunk_overlap configurable via settings
    splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=400)
    chunks = splitter.split_text(state.raw_content)
    logger.info("Split document into %d chunks", len(chunks))
    return {"chunks": chunks}


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
    # with_structured_output requires a top-level "title" to use as the function name
    schema = state.schema_definition
    if "title" not in schema:
        schema = {"title": "ExtractionResult", **schema}
    chain = llm.with_structured_output(schema)

    results: list[dict[str, Any]] = []
    for i, chunk in enumerate(state.chunks):
        base_prompt = (
            f"Extract data matching this schema: {json.dumps(state.schema_definition)}\n\n"
            f"Document content:\n{chunk}"
        )
        if state.retry_count > 0:
            # On a retry, prepend the previous errors so the LLM can self-correct
            error_prefix = (
                "Previous validation errors:\n" + "\n".join(state.last_validation_errors) + "\n\n"
            )
            prompt_str = error_prefix + base_prompt
        else:
            prompt_str = base_prompt

        try:
            result = await chain.ainvoke(prompt_str)
        except Exception as e:
            # If one chunk fails, record an empty result and continue rather
            # than aborting the whole job
            logger.warning("LLM call failed for chunk %d: %s", i, e)
            results.append({})
            continue

        # Normalise to plain dict regardless of what the LLM client returned
        if isinstance(result, dict):
            result_dict: dict[str, Any] = result
        else:
            # Pydantic model or other structured output
            try:
                result_dict = result.model_dump()  # type: ignore[union-attr]
            except AttributeError:
                result_dict = dict(result)  # type: ignore[call-overload]

        results.append(result_dict)
        logger.debug("Extracted chunk result: %s", list(result_dict.keys()))

    return {"chunk_extractions": results}


def _merge_chunks(
    chunk_extractions: list[dict[str, Any]],
    properties: dict[str, Any],
) -> dict[str, Any]:
    """Merge per-chunk extraction dicts respecting array vs scalar field types.

    Merge strategy:
      - Array fields  (schema type = "array"):  concatenate all chunk values
      - Scalar fields (everything else):        last chunk's value wins

    This is a pure helper — it has no side effects and is used by both
    validate_extraction (to check completeness) and merge_extractions (final merge).
    """
    merged: dict[str, Any] = {}
    for extraction in chunk_extractions:
        for field, value in extraction.items():
            if properties.get(field, {}).get("type") == "array":
                # Accumulate list items across chunks (e.g. line items in an invoice)
                existing = merged.get(field, [])
                if isinstance(existing, list) and isinstance(value, list):
                    merged[field] = existing + value
                else:
                    merged[field] = value
            else:
                # Scalar: last chunk wins (later chunks have more complete context)
                merged[field] = value
    return merged


async def validate_extraction(state: WorkflowState) -> dict[str, Any]:
    """Validate merged extractions against the schema's required fields.

    Merges all chunk extractions inline and checks that every field listed
    in ``required`` is present and non-empty in the combined result.  Returns
    updated retry state — callers should route back to extraction when errors
    are present and retries remain.

    NOTE: retry_count is incremented HERE (in validate), not in extract_structured.
    This is intentional: the router reads retry_count immediately after validate
    returns. If we incremented in extract, the counter would be wrong on the
    first-attempt path (it would show 1 even though no retry happened).
    """
    properties: dict[str, Any] = state.schema_definition.get("properties", {})
    merged = _merge_chunks(state.chunk_extractions, properties)

    required_fields: list[str] = state.schema_definition.get("required", [])
    errors: list[str] = []
    for field in required_fields:
        val = merged.get(field)
        if val is None or val == "":
            errors.append(f"Required field '{field}' is missing or empty")

    if errors:
        logger.warning("Validation failed with %d error(s)", len(errors))
        # Increment retry_count so the router knows another attempt has been used
        return {"last_validation_errors": errors, "retry_count": state.retry_count + 1}

    logger.info("Validation passed")
    return {"last_validation_errors": [], "retry_count": state.retry_count}


async def merge_extractions(state: WorkflowState) -> dict[str, Any]:
    """Merge per-chunk extractions into a single final result dict.

    For array-typed schema fields, values from all chunks are concatenated.
    For all other field types the last chunk's value takes precedence.
    The final status reflects whether validation was clean.
    """
    properties: dict[str, Any] = state.schema_definition.get("properties", {})
    merged = _merge_chunks(state.chunk_extractions, properties)

    # "completed_with_errors" means we hit max retries but still produced output
    status = "completed" if not state.last_validation_errors else "completed_with_errors"
    logger.info("Merge complete — status: %s", status)
    return {"final_result": merged, "status": status}
