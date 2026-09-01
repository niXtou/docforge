# DocForge

Upload a document → a LangGraph workflow extracts structured JSON against a Pydantic schema, retrying on validation failure → progress streams to a React frontend over SSE.

**[Live demo](https://docforge.nstoug.com)** · **[API docs](https://docforge.nstoug.com/docs)** · ![CI](https://github.com/niXtou/docforge/actions/workflows/deploy.yml/badge.svg)

---

## What it is

A project built to explore self-correcting LLM extraction workflows in LangGraph. The interesting bit isn't the upload-and-parse — it's that when the LLM's output fails Pydantic validation, the validation errors are fed back to the LLM as part of the retry prompt (up to three retries). This pattern keeps extraction reliable even with smaller, cheaper models.

The system ships with three pre-built schemas (Invoice, Resume/CV, Research Paper) and lets you define custom ones as JSON Schema.

---

## Architecture

```mermaid
graph TB
    UI[React Frontend] -->|HTTPS| API[FastAPI]
    API --> Parse[Parse document]
    Parse --> Chunk[Chunk text]
    Chunk --> Extract[Extract via LLM]
    Extract --> Validate{Pydantic validation}
    Validate -->|valid| Merge[Merge results]
    Validate -->|invalid + retries left| Extract
    Validate -->|max retries hit| Merge
    Merge --> API
    Extract -.->|OpenRouter| LLM[Claude / GPT / Gemini / OSS]
    API --> PG[(PostgreSQL)]
    API --> RD[(Redis)]
```

The workflow is a LangGraph state machine. Conditional edges route on Pydantic validation: valid → merge, invalid + retries left → re-extract with errors fed back into the prompt, max retries hit → return what we have.

Between extraction and validation a grounding step checks every value against the source text — first verbatim, then (in batches) with an LLM judge for anything not found literally. Values the judge rejects are dropped and the reason is fed into the retry prompt. Every value that survives carries its evidence: the snippet it was verified against and how (`verbatim`, `judge`, or `unverified`).

---

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI · Pydantic v2 · Python 3.12 |
| Workflow | LangGraph (state graph, conditional edges, structured output) |
| LLM routing | OpenRouter (Claude, GPT, Gemini, OSS) — BYOK supported |
| Storage | PostgreSQL 15 · Redis 7 (rate limiting) |
| Frontend | React 19 · TypeScript · Vite · Tailwind |
| Tooling | `uv` · `npm` · Ruff · Pyright (strict) · Vitest |
| Infra | Docker · Alembic · Nginx · GitHub Actions → ARM64 VPS |

---

## Quick start

Requires Docker and an [OpenRouter API key](https://openrouter.ai/keys) (or a direct provider key, used as BYOK).

```bash
cp .env.example .env       # add OPENROUTER_API_KEY
docker compose up --build
# API:      http://localhost:8000/docs
# Frontend: http://localhost:5173
```

---

## API at a glance

| Method | Path | Description |
|---|---|---|
| `GET`  | `/api/health` | Health check |
| `GET`  | `/api/schemas` | List extraction schemas |
| `POST` | `/api/schemas` | Create a custom schema |
| `POST` | `/api/extract` | Upload a document + start extraction |
| `GET`  | `/api/extract` | Recent jobs, newest first (`?limit=`, max 100) |
| `GET`  | `/api/extract/{id}/stream` | SSE stream of node-by-node progress |
| `GET`  | `/api/extract/{id}/result` | Final structured result |

Full interactive docs at `/docs` (Swagger UI). Demo mode rate-limits at 10 extractions/hour/IP and whitelists a small set of low-cost models. Passing your own OpenRouter key in the `api_key` multipart form field of `POST /api/extract` bypasses both.

The result carries the extracted `data` plus `validation_errors` (empty when validation passed) and `evidence` — one entry per value (`field`, or `field[i]` for array items) with the `quote` it was verified against, the `method` (`verbatim` / `judge` / `unverified`) and whether it was `supported`.

### What the stream shows

Each `node_completed` event says what the node did, not just that it ran: `chunk`/`extract` report the chunk count, `verify_grounding` reports rejected values and how many got evidence, `validate` reports its errors and the attempt number. When validation fails and the graph is about to loop back, a dedicated `retry` event is emitted with the attempt number and the exact errors being fed back to the model — the self-correcting loop is visible in the log rather than inferred from a second `validate` row.

---

## Development

```bash
# Backend
cd backend && uv sync --extra dev
uv run uvicorn app.main:app --reload     # :8000
uv run alembic upgrade head              # migrations

# Frontend
cd frontend && npm install
npm run dev                              # :5173
```

### Tests + quality gate

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pyright . && uv run pytest -v
cd frontend && npm run lint && npm run build && npm run test
```

Both run in CI on every push (`.github/workflows/deploy.yml`).

---

## Environment variables

See `.env.example` for the full list. Minimum: `OPENROUTER_API_KEY`. Postgres + Redis defaults work as-is under Docker Compose.

---

## License

MIT
