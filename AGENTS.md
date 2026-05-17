# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Cursor, etc.) working in this repo. See `README.md` for the project pitch.

## Project overview

DocForge is a FastAPI + LangGraph workflow that extracts structured JSON from documents (PDF, CSV, plain text) against a Pydantic schema, retrying on validation failure. Monorepo with `backend/` (Python 3.12) and `frontend/` (React 19 + TypeScript). Backed by PostgreSQL (extraction jobs + schemas) and Redis (rate limiting). Status: feature-complete, live at `docforge.nstoug.com`.

## Setup

```bash
# Backend
cd backend
uv sync --extra dev                  # installs runtime + dev deps (uv, NOT pip)

# Frontend
cd frontend
npm ci                                # uses npm, NOT pnpm
```

Environment: copy `.env.example` to `.env` and set `OPENROUTER_API_KEY` at minimum.

## Run

```bash
# Backend on :8000
cd backend && uv run uvicorn app.main:app --reload

# DB migrations
cd backend && uv run alembic upgrade head

# Frontend on :5173
cd frontend && npm run dev

# Full stack (backend + postgres + redis + frontend)
docker compose up --build
```

## Test

```bash
# Backend — full quality gate (must pass before committing)
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pyright . && uv run pytest -v

# Frontend
cd frontend && npm run lint && npm run build && npm run test

# Subsets while iterating
cd backend && uv run pytest tests/test_workflow.py -v
cd backend && uv run pytest -k "test_api" -v
```

CI runs the same commands on every push (see `.github/workflows/deploy.yml`).

## Code style

### Python (`backend/`)

- **Lint/format**: Ruff (replaces black, isort, flake8). Config in `pyproject.toml`. Line length 99, target `py312`.
- **Types**: Pyright in strict mode. All public functions get type hints on params and return values.
- **Async**: Use `async`/`await` throughout — no synchronous DB or HTTP calls.
- **Pydantic v2 only**: `model_validator`, `field_validator`, `ConfigDict`. Use `Field()` with descriptions.
- **SQLAlchemy 2.x**: `Mapped[]` annotations for ORM models, async session.
- **LangChain imports**: always from `langchain_core` (e.g. `from langchain_core.messages import HumanMessage`), never the top-level `langchain` package.
- **Logging**: use `logging`; no `print()` in production code.

### TypeScript (`frontend/`)

- Strict mode. No `any`.
- Functional components with hooks. Named exports.
- Tailwind for styling.

## Project layout

```
backend/app/
├── main.py              # FastAPI app factory + lifespan
├── api/                 # Route handlers (schemas, documents, health, deps)
├── core/                # Config, database, LLM factory, security
│   └── llm.py           # get_llm() — OpenRouter-first, BYOK support
├── models/              # db.py (SQLAlchemy), schemas.py (Pydantic)
├── services/            # Business logic (document processing, extraction)
└── workflows/           # LangGraph — the core extraction engine
    ├── state.py         # WorkflowState (Pydantic BaseModel)
    ├── nodes.py         # Async node functions
    └── graph.py         # Graph assembly + compilation

frontend/src/
├── api/                 # API client + SSE consumer
├── components/          # React UI
├── hooks/               # useSSE and friends
└── types/               # Shared TypeScript types
```

Key files to read first: `backend/app/workflows/graph.py` (graph assembly), `backend/app/core/config.py` (settings), `backend/app/core/llm.py` (LLM factory).

## Conventions

- **Streaming**: SSE via `sse-starlette`, not WebSockets.
- **LLM**: All calls go through `app/core/llm.py:get_llm()`, which returns a `ChatOpenRouter` from `langchain-openrouter`. Don't import provider SDKs directly.
- **LangGraph state**: Pydantic `BaseModel` (not `TypedDict`) — defined in `workflows/state.py`. Each node is an async function receiving `WorkflowState` and returning a partial state dict.
- **Conditional edges**: route on Pydantic validation. Valid → merge. Invalid + retries left → retry with validation errors injected into the prompt. Max 3 retries.
- **Structured output**: use `.with_structured_output(PydanticModel)` for extraction LLM calls.
- **Demo mode**: when `DEMO_MODE=true`, requests are validated against `DEMO_ALLOWED_MODELS` in `config.py` and rate-limited per IP via Redis (10/hour). Clients passing `X-API-Key` bypass both.
- **No secrets in code**: env vars only, via Pydantic Settings.
- **Library docs**: use `context7` MCP for current LangGraph / FastAPI / Pydantic / SQLAlchemy / OpenRouter docs — training data may be stale.

## Commit conventions

Format: `type(scope): description`

Types: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`. Scopes: `workflow`, `api`, `frontend`, `docker`, `ci`. Keep commits small and focused — one concern per commit.

## What to confirm before doing

- Adding or removing dependencies (`uv add`, `npm install`)
- Modifying `docker-compose*.yml` or any `Dockerfile`
- Modifying anything in `.github/workflows/` or `nginx/`
- Creating or editing files in `backend/alembic/versions/` (database migrations)
- Git operations beyond `status` / `diff` / `log` (especially `commit`, `push`, branch switches)
- Deleting files
