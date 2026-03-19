# PDF Parser Upgrade & Gemini Model ID Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two live bugs: (1) replace `google/gemini-2.0-flash` with the valid OpenRouter ID `google/gemini-2.0-flash-001` across all 17 affected files, and (2) replace PyPDF with `pymupdf4llm` in the PDF parse node to fix letter-spaced character extraction.

**Architecture:** Fix 1 is a global string replacement with one test-critical default change. Fix 2 replaces the PDF branch inside `parse_document` in `nodes.py` and swaps one dependency in `pyproject.toml`. No other nodes, API layer, or frontend logic is affected.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, uv, pymupdf4llm, pytest, Vitest

**Spec:** `docs/superpowers/specs/2026-03-19-pdf-parser-and-model-id-fixes-design.md`

---

## File Map

| File | Change |
|------|--------|
| `backend/app/workflows/state.py` | Model default → `google/gemini-2.0-flash-001` |
| `backend/app/models/schemas.py` | Model default → `google/gemini-2.0-flash-001` |
| `backend/app/core/config.py` | Allowlist default → `google/gemini-2.0-flash-001` |
| `backend/app/core/security.py` | Fallback default → `google/gemini-2.0-flash-001` |
| `backend/app/core/llm.py` | Param default + docstrings → `google/gemini-2.0-flash-001` |
| `backend/app/api/documents.py` | Form default → `google/gemini-2.0-flash-001` |
| `.env` | Allowlist value → `google/gemini-2.0-flash-001` |
| `.env.example` | Allowlist value → `google/gemini-2.0-flash-001` |
| `frontend/src/types/index.ts` | DEMO_MODELS id → `google/gemini-2.0-flash-001` |
| `frontend/src/App.tsx` | useState default → `google/gemini-2.0-flash-001` |
| `SOURCE_OF_TRUTH.md` | 5 occurrences → `google/gemini-2.0-flash-001` |
| `README.md` | curl example → `google/gemini-2.0-flash-001` |
| `backend/tests/test_models.py` | Default assertion → `google/gemini-2.0-flash-001` |
| `backend/tests/test_stage3.py` | 6 hardcoded strings → `google/gemini-2.0-flash-001` |
| `frontend/src/App.test.tsx` | 1 hardcoded string → `google/gemini-2.0-flash-001` |
| `frontend/src/api/client.test.ts` | 2 hardcoded strings → `google/gemini-2.0-flash-001` |
| `backend/pyproject.toml` | Remove `pypdf`, add `pymupdf4llm>=0.0.17` |
| `backend/app/workflows/nodes.py` | Replace PyPDF branch with pymupdf4llm |

---

## Task 1: Update all tests first (TDD anchor)

Update tests before touching source so that the test suite fails on the old values and passes once the source is fixed. `test_stage3.py` must be updated here too — once the backend allowlist is fixed in Task 2, the old model string will be rejected with 403, breaking those tests mid-plan.

**Files:**
- Modify: `backend/tests/test_models.py:32`
- Modify: `backend/tests/test_stage3.py` (6 occurrences)

- [ ] **Step 1.1: Update `test_models.py` assertion**

In `backend/tests/test_models.py`, change line 32:
```python
# Before
assert state.model == "google/gemini-2.0-flash"

# After
assert state.model == "google/gemini-2.0-flash-001"
```

- [ ] **Step 1.2: Update `test_stage3.py` (6 occurrences)**

`backend/tests/test_stage3.py` — replace all 6 occurrences (lines ~108, 152, 201, 238, 262, 292):
```python
# Before (6 occurrences)
"google/gemini-2.0-flash"

# After (6 occurrences)
"google/gemini-2.0-flash-001"
```

- [ ] **Step 1.3: Run the tests — confirm they fail**

```bash
cd backend
uv run pytest tests/test_models.py tests/test_stage3.py -v
```

Expected: `test_models.py` FAIL on the default assertion; `test_stage3.py` still passes (it sends the string to the API but the mock bypass means no 403 yet — this is expected). The key is `test_models.py` failing to anchor the TDD loop.

---

## Task 2: Fix backend model ID defaults and config

**Files:**
- Modify: `backend/app/workflows/state.py`
- Modify: `backend/app/models/schemas.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/security.py`
- Modify: `backend/app/core/llm.py`
- Modify: `backend/app/api/documents.py`

- [ ] **Step 2.1: Update `state.py`**

`backend/app/workflows/state.py` — find the `model` field default:
```python
# Before
model: str = "google/gemini-2.0-flash"  # OpenRouter model string

# After
model: str = "google/gemini-2.0-flash-001"  # OpenRouter model string
```

- [ ] **Step 2.2: Update `schemas.py`**

`backend/app/models/schemas.py` — find the `ExtractionRequest.model` field:
```python
# Before
    model: str = Field(default="google/gemini-2.0-flash")

# After
    model: str = Field(default="google/gemini-2.0-flash-001")
```

- [ ] **Step 2.3: Update `config.py`**

`backend/app/core/config.py` — find `demo_allowed_models` list default (this is the critical backend gate):
```python
# Before
            "google/gemini-2.0-flash",  # fast, very cost-effective

# After
            "google/gemini-2.0-flash-001",  # fast, very cost-effective
```

- [ ] **Step 2.4: Update `security.py`**

`backend/app/core/security.py` — find the fallback form value:
```python
# Before
    model = str(form.get("model", "google/gemini-2.0-flash"))

# After
    model = str(form.get("model", "google/gemini-2.0-flash-001"))
```

- [ ] **Step 2.5: Update `llm.py`**

`backend/app/core/llm.py` — update default parameter and any docstring references (3 occurrences):
```python
# Before (function signature)
    model: str = "google/gemini-2.0-flash",

# After
    model: str = "google/gemini-2.0-flash-001",
```
Also update any inline string in docstrings/module docstring referencing `google/gemini-2.0-flash`.

- [ ] **Step 2.6: Update `documents.py`**

`backend/app/api/documents.py` — find the Form default:
```python
# Before
    model: str = Form(default="google/gemini-2.0-flash"),

# After
    model: str = Form(default="google/gemini-2.0-flash-001"),
```

- [ ] **Step 2.7: Run test_models — confirm it passes now**

```bash
cd backend
uv run pytest tests/test_models.py -v
```

Expected: PASS

- [ ] **Step 2.8: Commit**

```bash
cd backend
git add app/workflows/state.py app/models/schemas.py app/core/config.py \
        app/core/security.py app/core/llm.py app/api/documents.py \
        tests/test_models.py
git commit -m "fix(api): update Gemini model ID to google/gemini-2.0-flash-001 in backend"
```

---

## Task 3: Fix frontend model ID + update frontend test fixtures

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/api/client.test.ts`

- [ ] **Step 3.1: Update `types/index.ts`**

`frontend/src/types/index.ts` — update DEMO_MODELS:
```typescript
// Before
  { id: 'google/gemini-2.0-flash', label: 'Gemini 2.0 Flash' },

// After
  { id: 'google/gemini-2.0-flash-001', label: 'Gemini 2.0 Flash' },
```

- [ ] **Step 3.2: Update `App.tsx`**

`frontend/src/App.tsx` line 18 — useState initial value:
```typescript
// Before
  const [model, setModel] = useState('google/gemini-2.0-flash')

// After
  const [model, setModel] = useState('google/gemini-2.0-flash-001')
```

- [ ] **Step 3.3: Update `App.test.tsx`**

`frontend/src/App.test.tsx` — update the hardcoded model_used fixture value:
```typescript
// Before
  model_used: 'google/gemini-2.0-flash',

// After
  model_used: 'google/gemini-2.0-flash-001',
```

- [ ] **Step 3.4: Update `client.test.ts`**

`frontend/src/api/client.test.ts` — update both occurrences (lines ~47, ~79):
```typescript
// Before
      model: 'google/gemini-2.0-flash',
// and
      model_used: 'google/gemini-2.0-flash',

// After
      model: 'google/gemini-2.0-flash-001',
// and
      model_used: 'google/gemini-2.0-flash-001',
```

- [ ] **Step 3.5: Run all tests**

```bash
cd backend && uv run pytest -v
cd ../frontend && npm run test
```

Expected: 23 backend tests pass, 16 frontend tests pass

- [ ] **Step 3.6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/App.tsx \
        frontend/src/App.test.tsx frontend/src/api/client.test.ts
git commit -m "fix(frontend): update Gemini model ID to google/gemini-2.0-flash-001"
```

---

## Task 4: Update docs and env files

**Files:**
- Modify: `.env`
- Modify: `.env.example`
- Modify: `SOURCE_OF_TRUTH.md`
- Modify: `README.md`

- [ ] **Step 4.1: Update `.env`**

`.env` — find `DEMO_ALLOWED_MODELS`:
```
# Before
DEMO_ALLOWED_MODELS=["anthropic/claude-sonnet-4-20250514","google/gemini-2.0-flash","openai/gpt-4o-mini","openai/gpt-5.4-nano"]

# After
DEMO_ALLOWED_MODELS=["anthropic/claude-sonnet-4-20250514","google/gemini-2.0-flash-001","openai/gpt-4o-mini","openai/gpt-5.4-nano"]
```

- [ ] **Step 4.2: Update `.env.example`**

Same change as above in `.env.example`.

- [ ] **Step 4.3: Update `SOURCE_OF_TRUTH.md`**

Replace all 5 occurrences of `google/gemini-2.0-flash` with `google/gemini-2.0-flash-001`. These appear in the LLM provider section, demo rate limiting section, env vars section, and deployment config examples.

- [ ] **Step 4.4: Update `README.md`**

Replace the 1 occurrence in the curl example.

- [ ] **Step 4.5: Update `docs/WORKFLOW.md`**

`docs/WORKFLOW.md` — line 46 contains the old model ID in a cost-comparison table:
```
# Before
| `google/gemini-2.0-flash` | $0.10 | $0.40 | Boilerplate, ...

# After
| `google/gemini-2.0-flash-001` | $0.10 | $0.40 | Boilerplate, ...
```

- [ ] **Step 4.6: Commit**

```bash
git add .env .env.example SOURCE_OF_TRUTH.md README.md docs/WORKFLOW.md
git commit -m "docs: update Gemini model ID to google/gemini-2.0-flash-001 in docs and config"
```

---

## Task 5: Swap PDF dependency — pymupdf4llm for pypdf

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 5.1: Edit `pyproject.toml`**

In `backend/pyproject.toml`, under `# Document Processing`:
```toml
# Before
    "pypdf>=4.0.0",
    "python-docx>=1.0.0",

# After
    "pymupdf4llm>=0.0.17",
    "python-docx>=1.0.0",
```

- [ ] **Step 5.2: Regenerate lockfile**

```bash
cd backend
uv lock
```

Expected: `uv.lock` updated with `pymupdf4llm` and its `pymupdf` transitive dependency; `pypdf` removed.

- [ ] **Step 5.3: Install updated deps**

```bash
uv sync --dev
```

Expected: `pymupdf4llm` installed, `pypdf` uninstalled.

- [ ] **Step 5.4: Verify no broken imports**

```bash
uv run python -c "import pymupdf4llm; print(pymupdf4llm.__version__)"
```

Expected: prints a version string without error.

- [ ] **Step 5.5: Commit**

```bash
cd /home/nikos/codebase/projects/docforge
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore(deps): replace pypdf with pymupdf4llm for PDF text extraction"
```

---

## Task 6: Replace PyPDF loader in parse_document

**Files:**
- Modify: `backend/app/workflows/nodes.py`

- [ ] **Step 6.1: Update the import line**

`backend/app/workflows/nodes.py` line 25 — remove `PyPDFLoader` from the import:
```python
# Before
from langchain_community.document_loaders import CSVLoader, PyPDFLoader, TextLoader

# After
from langchain_community.document_loaders import CSVLoader, TextLoader
```

Add `pymupdf4llm` import at the top of the file (with stdlib/third-party grouping per Ruff/isort):
```python
import pymupdf4llm
```

- [ ] **Step 6.2: Replace the PDF branch in `parse_document`**

Replace lines 42–49 (the PDF loader branch and loader variable setup):
```python
# Before (lines 42–67 of nodes.py — replace this entire block)
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
```

```python
# After
    if ext == ".pdf":
        # pymupdf4llm produces clean markdown — preserves word order in styled fonts.
        # Do NOT pass page_chunks=True; that changes the return type to list[dict].
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
```

- [ ] **Step 6.3: Run quality checks**

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pyright .
```

Expected: all clean, no errors.

- [ ] **Step 6.4: Run full backend test suite**

```bash
uv run pytest -v
```

Expected: 23/23 pass. (Tests mock the LLM and do not load real PDFs, so they are unaffected by the parser change.)

- [ ] **Step 6.5: Commit**

```bash
git add app/workflows/nodes.py
git commit -m "fix(workflow): replace PyPDF with pymupdf4llm for PDF text extraction"
```

---

## Task 7: Final verification

- [ ] **Step 7.1: Rebuild Docker image**

```bash
cd /home/nikos/codebase/projects/docforge
docker compose up --build -d
```

Wait for health:
```bash
curl -s http://localhost:8000/api/health
```
Expected: `{"status":"ok","database":"ok","version":"0.1.0"}`

- [ ] **Step 7.2: Smoke test — Gemini model ID**

Upload any document via `http://localhost:3000`, select **Gemini 2.0 Flash**, submit.
Expected: extraction completes without 400 errors in `docker compose logs backend`.

- [ ] **Step 7.3: Smoke test — CV full_name extraction**

Upload `my_cv.pdf`, select **Resume/CV** schema, any model.
Expected: `full_name` = `"Nikolaos Stougiannos"` in the results viewer.

- [ ] **Step 7.4: Run frontend tests**

```bash
cd frontend
npm run lint && npm run build && npm run test
```

Expected: lint clean, build succeeds, 16/16 tests pass.
