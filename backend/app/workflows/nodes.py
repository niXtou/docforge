"""Individual LangGraph node functions."""

import json
import logging
from pathlib import Path
from typing import Any

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import CSVLoader, PyPDFLoader, TextLoader

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

    docs = loader.load()
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
        return {"chunks": [state.raw_content]}

    splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=400)
    chunks = splitter.split_text(state.raw_content)
    logger.info("Split document into %d chunks", len(chunks))
    return {"chunks": chunks}


async def extract_structured(state: WorkflowState) -> dict[str, Any]:
    """Run structured extraction on each chunk using the configured LLM.

    Builds a prompt per chunk and invokes the LLM with structured-output
    mode so the response already conforms to the user-supplied JSON Schema.
    On retries the previous validation errors are prepended to the prompt.
    """
    llm = get_llm(model=state.model, api_key=state.api_key)
    chain = llm.with_structured_output(state.schema_definition)

    results: list[dict[str, Any]] = []
    for chunk in state.chunks:
        base_prompt = (
            f"Extract data matching this schema: {json.dumps(state.schema_definition)}\n\n"
            f"Document content:\n{chunk}"
        )
        if state.retry_count > 0:
            error_prefix = (
                "Previous validation errors:\n" + "\n".join(state.last_validation_errors) + "\n\n"
            )
            prompt_str = error_prefix + base_prompt
        else:
            prompt_str = base_prompt

        result = await chain.ainvoke(prompt_str)

        if isinstance(result, dict):
            result_dict: dict[str, Any] = result
        else:
            # Pydantic model or other structured output
            try:
                result_dict = result.dict()  # type: ignore[union-attr]
            except AttributeError:
                result_dict = dict(result)  # type: ignore[call-overload]

        results.append(result_dict)
        logger.debug("Extracted chunk result: %s", list(result_dict.keys()))

    return {"chunk_extractions": results}


async def validate_extraction(state: WorkflowState) -> dict[str, Any]:
    """Validate merged extractions against the schema's required fields.

    Merges all chunk extractions inline and checks that every field listed
    in ``required`` is present and non-empty in the combined result.  Returns
    updated retry state — callers should route back to extraction when errors
    are present and retries remain.
    """
    # Inline merge to validate the combined result
    merged: dict[str, Any] = {}
    properties: dict[str, Any] = state.schema_definition.get("properties", {})
    for extraction in state.chunk_extractions:
        for field, field_schema in properties.items():
            value = extraction.get(field)
            if value is None:
                continue
            field_type = field_schema.get("type", "")
            if field_type == "array":
                existing = merged.get(field, [])
                if isinstance(existing, list) and isinstance(value, list):
                    merged[field] = existing + value
                else:
                    merged[field] = value
            else:
                merged[field] = value

    required_fields: list[str] = state.schema_definition.get("required", [])
    errors: list[str] = []
    for field in required_fields:
        val = merged.get(field)
        if val is None or val == "":
            errors.append(f"Required field '{field}' is missing or empty")

    if errors:
        logger.warning("Validation failed with %d error(s)", len(errors))
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
    merged: dict[str, Any] = {}

    for extraction in state.chunk_extractions:
        for field, field_schema in properties.items():
            value = extraction.get(field)
            if value is None:
                continue
            field_type = field_schema.get("type", "")
            if field_type == "array":
                existing = merged.get(field, [])
                if isinstance(existing, list) and isinstance(value, list):
                    merged[field] = existing + value
                else:
                    merged[field] = value
            else:
                merged[field] = value

    status = "completed" if not state.last_validation_errors else "completed_with_errors"
    logger.info("Merge complete — status: %s", status)
    return {"final_result": merged, "status": status}
