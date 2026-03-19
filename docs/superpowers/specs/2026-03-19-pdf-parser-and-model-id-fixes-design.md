# Design: PDF Parser Upgrade & Gemini Model ID Fix

**Date:** 2026-03-19
**Status:** Approved
**Scope:** Two targeted bug fixes — no architectural changes

---

## Problem Summary

Two bugs discovered during live testing with `my_cv.pdf`:

1. **Invalid Gemini model ID** — `google/gemini-2.0-flash` returns HTTP 400 from OpenRouter on every LLM call. The correct versioned ID is `google/gemini-2.0-flash-001`. All extractions using this model silently fail with empty results and exhaust all 3 retries.

2. **PyPDF letter-spacing corruption** — PDFs with large styled header fonts are extracted with spaces between every character (`N i k o l a o s  S t o u g i a n n o s`). The LLM cannot reliably identify these as structured fields, causing `full_name` and similar fields to return empty or "Not provided" across all models.

---

## Fix 1: Gemini Model ID

### All affected locations (21 occurrences across 15 files)

| File | Change | Priority |
|------|--------|----------|
| `backend/app/core/config.py` | `demo_allowed_models` default list | **Critical** — gates all demo-mode requests |
| `backend/app/core/security.py` | fallback default in `require_demo_access` | **Critical** |
| `backend/app/workflows/state.py` | `model` field default | Important |
| `backend/app/models/schemas.py` | `ExtractionRequest.model` default | Important |
| `backend/app/api/documents.py` | `Form(default=...)` for upload endpoint | Important |
| `backend/app/core/llm.py` | module docstring + `get_llm()` default param + docstring | Cosmetic |
| `.env` | `DEMO_ALLOWED_MODELS` | Important |
| `.env.example` | `DEMO_ALLOWED_MODELS` | Important |
| `frontend/src/types/index.ts` | `DEMO_MODELS` id field | Important |
| `frontend/src/App.tsx` | `useState` initial value | Important |
| `backend/tests/test_models.py` | default model assertion (line 32) | Must update (test will fail) |
| `backend/tests/test_stage3.py` | 6 hardcoded model strings | Update for accuracy |
| `frontend/src/App.test.tsx` | 1 hardcoded model string | Update for accuracy |
| `frontend/src/api/client.test.ts` | 2 hardcoded model strings | Update for accuracy |
| `SOURCE_OF_TRUTH.md` | 5 occurrences in architecture/config sections | Important |
| `README.md` | 1 curl example | Cosmetic |

All occurrences (≈30 across 17 files): `google/gemini-2.0-flash` → `google/gemini-2.0-flash-001`

### Key Before/After for test-critical defaults

**`backend/app/workflows/state.py`**
```python
# Before
model: str = "google/gemini-2.0-flash"

# After
model: str = "google/gemini-2.0-flash-001"
```
Note: `backend/tests/test_models.py` line 32 asserts this default — it must be updated in sync or it will fail.

**`backend/app/models/schemas.py`**
```python
# Before
model: str = Field(default="google/gemini-2.0-flash")

# After
model: str = Field(default="google/gemini-2.0-flash-001")
```

### No migration needed

Config and constant change only. No DB schema change, no API contract change.

---

## Fix 2: PDF Parser — PyPDF → pymupdf4llm

### Why pymupdf4llm over pdfplumber

Both fix the letter-spacing issue. `pymupdf4llm` is preferred because:
- Purpose-built for LLM pipelines — outputs clean markdown preserving document structure
- Best-in-class word order preservation on complex layouts (highest BLEU-4 scores in 2026 benchmarks)
- Handles multi-column layouts, styled headers, and tables correctly
- `pdfplumber` is optimised for coordinate/table extraction, not prose text for LLMs

### Licensing note

`pymupdf4llm` depends on `PyMuPDF` (AGPL-3.0 / commercial dual-license). For this portfolio/demo project, AGPL-3.0 is acceptable. If DocForge ever becomes closed-source SaaS, a commercial PyMuPDF license would be required.

### Dependency changes (`backend/pyproject.toml`)

- Add: `pymupdf4llm>=0.0.17`
- Remove: `pypdf` — only used by `PyPDFLoader`; no longer needed
- `langchain-community` stays — still needed for `CSVLoader` and `TextLoader`
- After editing `pyproject.toml`, run `uv lock` to regenerate the lockfile

### Code change (`backend/app/workflows/nodes.py`)

**Before:**
```python
from langchain_community.document_loaders import CSVLoader, PyPDFLoader, TextLoader

if ext == ".pdf":
    loader: PyPDFLoader | CSVLoader | TextLoader = PyPDFLoader(state.file_path)
    # ...
    docs = await asyncio.to_thread(loader.load)
    text = "\n\n".join(doc.page_content for doc in docs)
    logger.info("Parsed %d document(s) from %s file", len(docs), ext)
    return {
        "raw_content": text,
        "file_type": ext,
        "messages": state.messages + [f"Parsed {len(docs)} document(s) from {ext} file"],
    }
```

**After:**
```python
import pymupdf4llm
from langchain_community.document_loaders import CSVLoader, TextLoader

if ext == ".pdf":
    # pymupdf4llm.to_markdown returns a single markdown string.
    # Do NOT pass page_chunks=True — that returns list[dict] instead of str.
    try:
        text = await asyncio.to_thread(pymupdf4llm.to_markdown, state.file_path)
    except Exception as e:
        raise FileNotFoundError(f"Could not read file {state.file_path}: {e}") from e
    logger.info("Parsed PDF document from %s", state.file_path)
    return {
        "raw_content": text,
        "file_type": ext,
        "messages": state.messages + ["Parsed PDF document"],
    }
```

The `try/except` guard is preserved — `pymupdf4llm.to_markdown` raises its own exception types but the pattern of wrapping in `FileNotFoundError` is maintained for consistent error surfaces upstream.

Non-PDF branches (CSV, TXT, MD) are unchanged. The `loader` variable and `docs` variable are only used in the PDF branch, so removing them causes no side effects elsewhere.

---

## Testing

- `uv run pytest -v` — all 23 tests must pass (LLM is mocked; PDF parsing is not unit-tested)
- `uv run ruff check . && uv run ruff format --check . && uv run pyright .` — must be clean
- Manual smoke test: upload `my_cv.pdf` → Resume/CV schema → `full_name` must return `"Nikolaos Stougiannos"`
- Manual smoke test: select Gemini 2.0 Flash in UI → extraction must complete without 400 errors

---

## Out of Scope

- No new unit tests for PDF parsing (requires fixture PDFs — deferred to a future quality pass)
- No model allowlist expansion beyond correcting the existing Gemini entry
- No changes to chunking, validation, merge, or SSE logic
