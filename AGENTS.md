# AGENTS.md

## Project overview

DocForge is an AI-powered document intelligence API. Users upload documents, select extraction schemas, and receive structured JSON via a self-correcting LangGraph agent workflow. Monorepo with `backend/` (FastAPI + Python 3.12) and `frontend/` (React 19 + TypeScript + Vite).

Architecture and data models are defined in `SOURCE_OF_TRUTH.md` — always read it before making structural changes.

## Setup commands

```bash
# Backend
cd backend
uv sync                              # install deps (uses uv, NOT pip)
uv run uvicorn app.main:app --reload # dev server on :8000
uv run alembic upgrade head          # run migrations

# Frontend
cd frontend
npm ci                               # install deps
npm run dev                          # dev server on :5173

# Full stack (local)
docker compose up --build            # backend + postgres + redis + frontend

# Verify
curl http://localhost:8000/api/health
```

## Testing

```bash
# Backend — always run before committing
cd backend
uv run pytest -v                     # unit + integration tests
uv run pytest tests/test_workflow.py # workflow tests only (mocked LLM)
uv run pytest -k "test_api"         # API tests only

# Frontend
cd frontend
npm run test                         # vitest

# Full quality check (must all pass before merging to main)
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pyright . && uv run pytest -v
cd frontend && npm run lint && npm run build && npm run test
```

When adding new features, write or update tests first. For regressions, add a failing test that reproduces the bug, then fix to green.

## Code style

### Python (backend/)

- **Formatter/linter**: Ruff (replaces black, isort, flake8). Config in `pyproject.toml`.
- **Type checker**: Pyright in strict mode.
- All functions must have type hints for parameters and return values.
- Use `async`/`await` throughout — no synchronous database or HTTP calls.
- Pydantic v2 `BaseModel` for all data schemas. Use `Field()` with descriptions. Use `model_config = ConfigDict(strict=True)` where appropriate.
- SQLAlchemy 2.x `Mapped[]` annotations for ORM models.
- Imports: stdlib → third-party → local, enforced by Ruff.
- Max line length: 99 (configured in Ruff).
- Docstrings: Google style, required on public functions and classes.

### TypeScript (frontend/)

- Strict TypeScript — no `any` types.
- Functional React components with hooks only (no class components).
- Tailwind CSS for styling — no CSS modules, no styled-components.
- Use named exports (not default exports) for components.

### General

- No `console.log` / `print()` in production code. Use proper logging (`logging` module in Python).
- Environment variables via Pydantic Settings (`app/core/config.py`). Never hardcode secrets or API keys.

## Project structure

```
backend/app/
├── main.py              # FastAPI app factory + lifespan
├── api/                 # Route handlers (schemas.py, documents.py, health.py, deps.py)
├── core/                # Config, database, LLM factory, security
│   └── llm.py           # get_llm() — OpenRouter-first, BYOK support
├── models/              # db.py (SQLAlchemy), schemas.py (Pydantic)
├── services/            # Business logic (document processing, extraction)
└── workflows/           # LangGraph — the core extraction engine
    ├── state.py          # WorkflowState (Pydantic BaseModel)
    ├── nodes.py          # Individual node functions
    └── graph.py          # Graph assembly + compilation

frontend/src/
├── api/client.ts        # API client + SSE consumer
├── components/          # React components
├── hooks/useSSE.ts      # Custom SSE hook
└── types/index.ts       # Shared TypeScript types
```

Key files to read first: `SOURCE_OF_TRUTH.md` (architecture), `backend/app/workflows/graph.py` (core logic), `backend/app/core/config.py` (all settings).

## LangGraph conventions

- Graph state uses Pydantic `BaseModel` (not `TypedDict`) — defined in `workflows/state.py`.
- Each node is an async function in `workflows/nodes.py` receiving `WorkflowState`, returning a partial state dict.
- Conditional edges route on validation: valid → merge, invalid + retries left → retry, failed → error.
- Use `.with_structured_output(PydanticModel)` for LLM extraction calls.
- Max 3 retries. Feed Pydantic validation errors back to the LLM on retry.

## LLM provider pattern

All LLM calls go through `app/core/llm.py:get_llm()`. Returns a LangChain `ChatOpenAI` pointed at OpenRouter (`base_url="https://openrouter.ai/api/v1"`). Do NOT import provider SDKs directly elsewhere. BYOK (user-provided API key) is handled per-request, not per-module.

## Docker

- Backend Dockerfile: multi-stage with `uv` (not pip). Non-root user in runtime stage.
- Frontend Dockerfile: multi-stage — `npm ci && npm run build` → output to shared volume.
- Local: `docker-compose.yml`. Production: `docker-compose.prod.yml`.
- All services must define health checks.
- Target architecture: ARM64 (Hetzner cax11).

## Permissions

### Allowed without prompting

- Read any file, list directories
- Run linters: `uv run ruff check .`, `uv run ruff format .`, `uv run pyright .`
- Run tests: `uv run pytest`, `npm run test`
- Run builds: `npm run build`
- Edit source files in `backend/app/` and `frontend/src/`
- Create new test files in `backend/tests/` and `frontend/src/tests/`

### Require confirmation

- Adding or removing dependencies (`uv add`, `npm install`)
- Modifying `docker-compose*.yml`, `Dockerfile`, or `nginx/` configs
- Modifying `alembic/versions/` (database migrations)
- Git operations (`git commit`, `git push`)
- Any changes to `SOURCE_OF_TRUTH.md` or `AGENTS.md`
- Deleting files

## Commit conventions

Format: `type(scope): description`

- Types: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`
- Scopes: `workflow`, `api`, `frontend`, `docker`, `ci`
- Keep diffs small and focused — one concern per commit.

## When stuck

- Ask a clarifying question or propose a short plan. Do not push large speculative changes.
- If a test fails unexpectedly, re-run with `uv run pytest -v --tb=long`.
- For dependency issues, check `uv.lock` and version constraints in `pyproject.toml`.
- For LangGraph architecture questions, consult `SOURCE_OF_TRUTH.md` Section 2.3.
