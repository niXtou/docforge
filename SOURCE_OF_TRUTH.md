# DocForge — Source of Truth

> **Last updated**: 2026-03-20
> **Status**: Stages 1–6 complete + production hardening
> **Author**: nstoug
> **Live demo target**: `docforge.nstoug.com`
> **Repository**: `github.com/niXtou/docforge`

---

## 1. Project Overview

**DocForge** is an AI-powered document intelligence API and web application. Users upload documents (PDF, CSV, plain text), define or select extraction schemas, and receive structured, validated JSON — powered by a self-correcting LangGraph agent workflow with Pydantic validation at every step.

### Why This Project Exists

1. **Portfolio proof**: Demonstrates production-grade AI engineering — not a wrapper around an API call, but a stateful, multi-step, self-correcting agent system with proper infrastructure.
2. **Skill showcase**: LangGraph, FastAPI, Pydantic v2, async SQLAlchemy, Docker, and modern Python tooling.
3. **Potential micro-SaaS seed**: Document extraction is a real paid problem. If the demo gains traction, it can evolve into a product.
4. **Freelance leverage**: A live demo at `docforge.nstoug.com` linked from your portfolio is concrete evidence of capability when pitching to clients.

### What Makes It Non-Trivial

- **Self-correcting extraction loop**: LangGraph graph with conditional retry edges — the LLM gets its own Pydantic validation errors fed back and retries (max 3 attempts). This is the pattern production AI systems use.
- **Multi-provider LLM routing**: `langchain-openrouter` as primary integration — one API key routes to Claude, GPT-4o, Gemini, and open-source models. BYOK (Bring Your Own Key) per request.
- **Real-time streaming**: SSE (Server-Sent Events) from LangGraph node transitions to the frontend via a background-task decoupled architecture that survives client disconnects.
- **Schema-driven extraction**: Users define JSON Schema extraction targets. The system dynamically constructs extraction prompts and validates output against them.

---

## 2. Architecture

### 2.1 System Diagram (C4 Level 2)

```
┌──────────────────────────────────────────────────────────────────┐
│  Cloudflare (Proxied DNS, Full Strict SSL, HSTS, Bot Fight Mode)  │
│  nstoug.com / docforge.nstoug.com → Hetzner VPS :443             │
└──────────────┬───────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────┐
│  Hetzner VPS — cax11 (ARM64, 2 vCPU, 4 GB RAM)                   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Gateway Nginx  (niXtou/hetzner-vps-portfolio-infra)         │ │
│  │  :80  → redirect to :443                                     │ │
│  │  :443 TLS — Cloudflare Origin wildcard cert (*.nstoug.com)   │ │
│  │  nstoug.com          → portfolio-nginx:80   (gateway_net)    │ │
│  │  docforge.nstoug.com → docforge-frontend:80 (gateway_net)    │ │
│  └────────────────────────────┬─────────────────────────────────┘ │
│                               │  Docker network: gateway_net       │
│              ┌────────────────▼────────────────┐                   │
│              │  DocForge frontend nginx (:80)   │                   │
│              │  /         → React SPA           │                   │
│              │  /api/*    → backend:8000 (SSE)  │                   │
│              └────────────────┬────────────────┘                   │
│                               │  Docker network: internal          │
│              ┌────────────────▼────────────────┐                   │
│              │  Backend (FastAPI + Uvicorn)     │                   │
│              │  ┌──────────────────────────┐   │                   │
│              │  │  LangGraph Workflow       │   │                   │
│              │  │  Parse→Chunk→Extract      │   │                   │
│              │  │  Validate ↺ (max 3)       │   │                   │
│              │  │  Merge→Done               │   │                   │
│              │  └──────────────────────────┘   │                   │
│              └──────────┬──────────┬───────────┘                   │
│                    ┌────▼───┐  ┌───▼────┐                          │
│                    │Postgres│  │ Redis  │   (internal only)         │
│                    └────────┘  └────────┘                          │
│                                    │                               │
│                            ┌───────▼──────┐                        │
│                            │  OpenRouter  │  (external API)         │
│                            └─────────────┘                         │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Network & DNS Configuration

| Record | Type | Content | Proxy | Notes |
|--------|------|---------|-------|-------|
| `docforge` | A | `<VPS IP>` | Proxied 🟠 | Same pattern as `api.nstoug.com` |

**SSL**: Cloudflare Full (Strict) with Cloudflare Origin Certificate (`*.nstoug.com` wildcard covering all subdomains). HSTS enabled at Cloudflare edge (6-month max-age, includeSubDomains).

**Multi-project gateway pattern** (`niXtou/hetzner-vps-portfolio-infra`):
```
~/
├── portfolio/                        # my-portfolio-site stack
├── docforge/                         # DocForge stack
└── hetzner-vps-portfolio-infra/      # gateway (owns ports 80/443)
    ├── docker-compose.yml
    └── nginx/nginx.conf              # server block per project
```

Each project joins the shared `gateway_net` Docker network with a stable alias. Adding a project: add an upstream + server block to nginx.conf, `docker compose up -d --force-recreate`. No changes to other projects.

### 2.3 LangGraph Workflow (Core Logic)

```
                    ┌─────────┐
                    │  START  │
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  parse  │  ← Detect file type, extract raw text
                    │         │    (PyPDFLoader / TextLoader / CSVLoader)
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  chunk  │  ← Split into processable segments
                    │         │    (RecursiveCharacterTextSplitter)
                    └────┬────┘
                         │
                    ┌────▼─────┐
                    │ extract  │  ← LLM call: prompt + schema → structured output
                    │          │    Uses .with_structured_output(json_schema)
                    │          │    (prepends "ExtractionResult" title to schema)
                    └────┬─────┘
                         │
                    ┌────▼──────┐
                    │ validate  │  ← Check required fields; collect error list
                    └────┬──────┘
                         │
                    ┌────▼────┐        ┌───────────┐
                    │  route  │──No───▶│  retry    │
                    │ valid?  │        │ (feed     │
                    └────┬────┘        │  errors   │
                         │Yes          │  to LLM)  │
                         │             └─────┬─────┘
                         │             (max 3 retries,
                         │              then proceed anyway)
                         │                   │
                    ┌────▼────┐              │
                    │  merge  │◀─────────────┘
                    │         │  ← Combine chunk-level extractions
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │   END   │  → final_result in WorkflowState
                    └─────────┘
```

**Graph state** (`app/workflows/state.py`):
```python
class WorkflowState(BaseModel):
    # Input — set by caller before graph starts
    document_id: str
    file_path: str = ""
    file_type: str = ""
    raw_content: str = ""
    schema_definition: dict          # JSON Schema the LLM must conform to
    model: str = "google/gemini-2.0-flash-001"
    api_key: str | None = None       # BYOK; None = use server key

    # Processing — filled in by nodes
    chunks: list[str] = []
    current_chunk_index: int = 0
    chunk_extractions: list[dict] = []

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    last_validation_errors: list[str] = []

    # Output — set by merge_extractions
    final_result: dict | None = None
    status: str = "pending"          # completed | completed_with_errors | failed
    messages: list[str] = []
```

**SSE background-task design** (`app/services/extraction.py`):

`POST /api/extract` saves the file and creates a DB job returning `202 pending` immediately. The SSE endpoint (`GET /api/extract/{job_id}/stream`) triggers extraction by:

1. Committing `status="processing"` on the request session
2. Spawning `_run_extraction_task` as an `asyncio.create_task` with its own `AsyncSessionLocal` session
3. Yielding `StreamEvent` objects from a shared `asyncio.Queue`

The background task is independent of the SSE connection — if the client disconnects, the task continues and commits the result. This is the correct design for long-running LLM workflows with streaming.

---

## 3. Tech Stack

| Layer | Choice | Version | Rationale |
|-------|--------|---------|-----------|
| Language | Python | 3.12 | Stable across full dependency tree |
| Package manager | uv | latest | Fast, reproducible — replaces pip/poetry/pipenv |
| API framework | FastAPI | 0.115+ | Native Pydantic v2, async-first, auto OpenAPI |
| Data validation | Pydantic | v2 | State schemas, API models, LLM structured output |
| Agent orchestration | LangGraph | 1.x | Production-grade stateful agent workflows |
| LLM integrations | LangChain | 0.3.x | Document loaders, text splitters, model wrappers |
| LLM routing | langchain-openrouter | 0.1+ | First-party LangChain × OpenRouter integration (2026) |
| Database | PostgreSQL | 15 | Stores schemas, jobs, results |
| Cache / rate limiting | Redis | 7 | IP-based demo rate limiting |
| ORM | SQLAlchemy | 2.x async | Async session, Alembic migrations |
| Migrations | Alembic | latest | Schema versioning |
| Frontend | React 19 + Vite + TS + Tailwind | — | SPA with real-time SSE streaming |
| Containerization | Docker Compose | — | Multi-stage builds, health checks |
| CI/CD | GitHub Actions | — | SSH deploy to Hetzner |
| DNS / SSL | Cloudflare | Full Strict | Origin certificates, WAF |
| Linting / Formatting | Ruff | latest | Replaces black + isort + flake8 |
| Type checking | Pyright | strict | Better Pydantic v2 support than mypy |
| Testing | pytest + httpx + pytest-asyncio | — | Async test support |

### Python Dependencies (`backend/pyproject.toml`)

```toml
[project]
name = "docforge"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    # API
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "python-multipart>=0.0.9",      # multipart file uploads

    # Data
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29.0",              # async Postgres driver
    "alembic>=1.13.0",
    "redis>=5.0.0",

    # AI / LLM
    "langgraph>=1.0.0",
    "langchain>=0.3.0",
    "langchain-openrouter>=0.1.0",  # first-party OpenRouter integration
    "langchain-anthropic>=0.3.0",
    "langchain-google-genai>=2.0.0",
    "langchain-community>=0.3.0",   # document loaders
    "langchain-text-splitters>=0.3.0",

    # Validation & Config
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",

    # Document Processing
    "pymupdf4llm>=0.0.17",          # PDF → Markdown (high-fidelity)
    "python-docx>=1.0.0",           # DOCX support

    # Utilities
    "httpx>=0.27.0",
    "sse-starlette>=2.0.0",         # SSE streaming
    "python-jose[cryptography]>=3.3.0",  # JWT (future auth)
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
    "ruff>=0.6.0",
    "pyright>=1.1.380",
    "pre-commit>=3.8.0",
    "aiosqlite>=0.20.0",            # in-memory SQLite for tests
]
```

---

## 4. Repository Structure

```
docforge/
├── .github/
│   └── workflows/
│       └── deploy.yml              # CI/CD: test → build → SSH deploy
├── AGENTS.md                       # AI agent collaboration guide
├── SOURCE_OF_TRUTH.md              # This document
├── README.md                       # Public-facing project README
├── .gitignore
├── .pre-commit-config.yaml
├── docker-compose.yml              # Local development (backend + postgres + redis + frontend)
├── docker-compose.prod.yml         # Production (+ nginx + frontend)
├── .env.example                    # Template for required env vars
│
├── backend/
│   ├── Dockerfile                  # Multi-stage: uv install → slim runtime (non-root)
│   ├── pyproject.toml              # uv-managed dependencies + ruff/pyright/pytest config
│   ├── uv.lock                     # Lockfile (commit to repo)
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   │       └── 0001_initial_schema_with_stage_3_columns.py
│   └── app/
│       ├── main.py                 # FastAPI app factory + lifespan (seeds builtins)
│       ├── api/
│       │   ├── router.py           # Mounts health, schemas, documents routers
│       │   ├── health.py           # GET /api/health — DB + Redis liveness
│       │   ├── schemas.py          # GET/POST /api/schemas — schema CRUD
│       │   ├── documents.py        # POST/GET /api/extract — upload, stream, result
│       │   └── deps.py             # get_db() dependency (overridable in tests)
│       ├── core/
│       │   ├── config.py           # Pydantic Settings (env-based, singleton)
│       │   ├── database.py         # Async SQLAlchemy engine + session factory
│       │   ├── redis.py            # Lazy Redis singleton (get_redis / close_redis)
│       │   ├── security.py         # Model whitelist + IP rate limiting + require_demo_access
│       │   └── llm.py              # get_llm() — ChatOpenRouter factory (BYOK support)
│       ├── models/
│       │   ├── db.py               # SQLAlchemy ORM: ExtractionSchema, ExtractionJob
│       │   └── schemas.py          # Pydantic: request/response models, StreamEvent
│       ├── services/
│       │   └── extraction.py       # Glue layer: DB lifecycle + LangGraph orchestration
│       └── workflows/
│           ├── state.py            # WorkflowState (Pydantic BaseModel)
│           ├── nodes.py            # Node functions: parse, chunk, extract, validate, merge
│           └── graph.py            # Graph assembly, conditional edges, compiled_graph
│
├── tests/
│   ├── conftest.py                 # Fixtures: async SQLite DB, seeded_schema, test client
│   ├── test_api.py                 # Health endpoint tests
│   ├── test_models.py              # Pydantic model validation tests
│   ├── test_workflow.py            # LangGraph workflow tests (mocked LLM)
│   └── test_stage3.py              # Schema CRUD + extraction endpoint tests
│
├── frontend/
│   ├── Dockerfile                  # Multi-stage: node:22-alpine build → nginx:1.25-alpine serve
│   ├── nginx.conf                  # SPA fallback + /api/ proxy to backend:8000 (SSE-safe headers)
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── src/
│       ├── App.tsx                 # 4-step wizard: upload → streaming → results
│       ├── App.test.tsx            # Vitest: renders, extract disabled, form submit
│       ├── api/
│       │   ├── client.ts           # Typed fetch wrappers: listSchemas, uploadDocument, getResult, streamUrl
│       │   └── client.test.ts      # 6 tests using vi.spyOn(globalThis, 'fetch')
│       ├── components/
│       │   ├── Layout.tsx          # Sticky header + main + footer shell
│       │   ├── DocumentUpload.tsx  # Drag-and-drop, click-to-upload, .pdf/.txt/.csv/.md validation
│       │   ├── SchemaSelector.tsx  # Dropdown + "view schema" JSON modal
│       │   ├── ModelSelector.tsx   # Radio-group (not select — avoids combobox aria conflicts)
│       │   ├── ApiKeyInput.tsx     # BYOK toggle switch + password field with show/hide
│       │   ├── ExtractionProgress.tsx  # 5-node stepper matching LangGraph node names
│       │   └── ResultsViewer.tsx   # Stats row + JSON/table toggle + copy-to-clipboard
│       ├── hooks/
│       │   ├── useSSE.ts           # EventSource hook → events[], SSEStatus, error, reset()
│       │   └── useSSE.test.ts      # 7 tests with MockEventSource via vi.stubGlobal
│       ├── test/
│       │   └── setup.ts            # Vitest setup: @testing-library/jest-dom + NoopEventSource stub
│       └── types/index.ts          # Schema, ExtractionJobResponse, ExtractionResult, StreamEvent, DEMO_MODELS
│
└── docker-compose.prod.yml         # Production stack (pulled from GHCR, joins gateway_net)
```

---

## 5. API Specification

### Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/health` | Health check (DB + Redis) | None |
| `GET` | `/api/schemas` | List extraction schemas | None |
| `GET` | `/api/schemas/{id}` | Get schema by ID | None |
| `POST` | `/api/schemas` | Create custom schema | None (rate-limited) |
| `POST` | `/api/extract` | Upload document, create pending job | Demo rate limit or BYOK |
| `GET` | `/api/extract/{job_id}/stream` | SSE: stream extraction progress | None |
| `GET` | `/api/extract/{job_id}/result` | Final extraction result | None |
| `GET` | `/docs` | Swagger UI (auto-generated) | None |

### Pydantic Models

```python
# ── Request Models ────────────────────────────────────────────────────────────

class SchemaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="")
    json_schema: dict[str, object]

class ExtractionRequest(BaseModel):
    schema_id: int = Field(..., gt=0)
    model: str = Field(default="google/gemini-2.0-flash-001")
    api_key: str | None = None  # BYOK — bypasses rate limits and model whitelist

# ── Response Models ───────────────────────────────────────────────────────────

class SchemaResponse(BaseModel):
    id: int
    name: str
    description: str
    json_schema: dict[str, object]
    is_builtin: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class ExtractionJobResponse(BaseModel):
    """Returned immediately on POST /api/extract (202 Accepted)."""
    job_id: str
    status: str          # always "pending" at creation
    schema_name: str
    created_at: datetime

class ExtractionResult(BaseModel):
    """Returned by GET /api/extract/{job_id}/result once complete."""
    job_id: str
    status: str          # completed | completed_with_errors | failed
    data: dict | None    # extracted fields; None if job failed
    validation_passed: bool
    retries_used: int
    model_used: str
    processing_time_ms: int
    chunks_processed: int

class StreamEvent(BaseModel):
    """SSE payload emitted per LangGraph node transition."""
    event: str           # node_completed | error | done
    node: str | None
    message: str
    timestamp: datetime
    data: dict | None = None

class ErrorResponse(BaseModel):
    """Standard structured error body (used in 403, 429 responses)."""
    detail: str
    code: str | None = None  # "rate_limit_exceeded" | "model_not_allowed"
```

### Pre-built Extraction Schemas

| Schema | Required Fields | Optional Fields |
|--------|----------------|-----------------|
| **Invoice** | `invoice_number`, `total_amount` | `vendor_name`, `invoice_date` |
| **Resume/CV** | `full_name` | `email`, `phone`, `skills[]` |
| **Research Paper** | `title`, `authors[]`, `abstract` | `keywords[]` |

---

## 6. Data Models (Database)

### SQLAlchemy ORM (`app/models/db.py`)

```python
class ExtractionSchema(Base):
    __tablename__ = "extraction_schemas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    json_schema: Mapped[dict] = mapped_column(JSON)
    is_builtin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    jobs: Mapped[list["ExtractionJob"]] = relationship(back_populates="schema")


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)   # UUID
    schema_id: Mapped[int] = mapped_column(ForeignKey("extraction_schemas.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    original_filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(10))
    model_used: Mapped[str] = mapped_column(String(100))

    # Populated after graph completes
    result_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_passed: Mapped[bool | None] = mapped_column(nullable=True)
    retries_used: Mapped[int] = mapped_column(default=0)
    processing_time_ms: Mapped[int | None] = mapped_column(nullable=True)
    chunks_processed: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=func.now())

    # SSE two-phase design: stored on job so stream endpoint can resume
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    schema: Mapped["ExtractionSchema"] = relationship(back_populates="jobs")
```

**Status lifecycle**: `pending` → `processing` → `completed` | `completed_with_errors` | `failed`

**Alembic**: One migration covers the full schema (`alembic/versions/0001_initial_schema_with_stage_3_columns.py`). Run `alembic upgrade head` on first deploy.

---

## 7. LLM Provider Architecture

### OpenRouter via `langchain-openrouter`

```python
# app/core/llm.py
from langchain_openrouter import ChatOpenRouter
from app.core.config import settings

def get_llm(
    model: str = "google/gemini-2.0-flash-001",
    api_key: str | None = None,
    temperature: float = 0.0,
) -> ChatOpenRouter:
    effective_key = api_key or settings.openrouter_api_key

    return ChatOpenRouter(
        model=model,
        api_key=effective_key,
        temperature=temperature,
        app_url="https://docforge.nstoug.com",
        app_title="DocForge",
    )
```

`langchain-openrouter` is the official first-party LangChain integration for OpenRouter, released in early 2026. It exposes the same `ChatOpenAI`-compatible interface and natively handles OpenRouter's provider routing, attribution headers, and structured output.

**BYOK flow**: The API key is passed per-request in the multipart form body, stored on `ExtractionJob.api_key`, and forwarded to `get_llm()` by the extraction service. BYOK users bypass both the model whitelist and the Redis rate limiter entirely.

### Demo Rate Limiting (`app/core/security.py`)

Redis INCR + EXPIRE per client IP. 1-hour sliding window.

```python
# Model whitelist (demo mode — no api_key provided)
demo_allowed_models = [
    "google/gemini-2.0-flash-001",              # fast, very cost-effective
    "openai/gpt-4o-mini",                   # good reasoning at low cost
    "openai/gpt-5.4-nano",                  # latest nano
    "meta-llama/llama-3.3-70b-instruct",    # open-weight, cheap via OpenRouter
]
demo_rate_limit_per_hour = 10  # per IP
```

The `require_demo_access` FastAPI dependency reads `model` and `api_key` directly from `request.form()` so it works alongside `UploadFile` without a duplicate form parse.

---

## 8. Deployment Configuration

### Backend Dockerfile (multi-stage with uv)

```dockerfile
# Stage 1: Builder — install deps with uv
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-editable
COPY app/ app/
COPY alembic.ini alembic/ ./

# Stage 2: Runtime — lean image, no build tools, non-root user
FROM python:3.12-slim AS runtime
RUN groupadd -r appuser && useradd -r -g appuser appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/alembic /app/alembic
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

### Frontend Dockerfile (multi-stage)

```dockerfile
# Stage 1: Build (--platform=$BUILDPLATFORM runs npm on native x86 CI runner,
# avoiding QEMU illegal-instruction crash with Node on ARM64 emulation)
FROM --platform=$BUILDPLATFORM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:1.25-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

The `nginx.conf` baked into the image proxies `/api/` to `backend:8000` with SSE-safe settings (`proxy_buffering off`, `proxy_http_version 1.1`, `Connection ''`, `proxy_read_timeout 300s`) and serves the SPA with a `try_files` fallback.

### Docker Compose (local development)

Four services: `backend`, `db` (Postgres 15), `redis` (Redis 7), `frontend` (nginx serving React build on port 3000). Backend mounts `./backend/app` for hot reload. Services declare health checks so the backend only starts after Postgres and Redis are ready.

### Docker Compose (production — `docker-compose.prod.yml`)

Four services pulled from GHCR. No host port bindings — traffic arrives from the gateway nginx via `gateway_net`. Target architecture: ARM64 (Hetzner cax11).

| Service | Image | Networks | Notes |
|---------|-------|----------|-------|
| `backend` | `ghcr.io/nixtou/docforge-backend:latest` | internal | resource limits: 1.5 CPU / 1500M |
| `frontend` | `ghcr.io/nixtou/docforge-frontend:latest` | internal + gateway_net | alias: `docforge-frontend` |
| `db` | `postgres:15-alpine` | internal | volume: `docforge_pgdata` |
| `redis` | `redis:7-alpine` | internal | volume: `docforge_redisdata` |

`gateway_net` is declared `external: true` — created once by `hetzner-vps-portfolio-infra` (`docker network create gateway_net`).

### CI/CD (`.github/workflows/deploy.yml`)

Three jobs, all third-party actions pinned to commit SHAs:

1. **test**: ruff + pyright + pytest (backend); eslint + vitest (frontend)
2. **build-push**: QEMU ARM64 cross-compile → push `ghcr.io/nixtou/docforge-{backend,frontend}:latest`
3. **deploy**: SCP `docker-compose.prod.yml` to VPS → SSH → pull → `alembic upgrade head` → `docker compose up -d`

---

## 9. Environment Variables

```env
# .env.example

# === App ===
SECRET_KEY=change-me-to-random-string
DEBUG=False
# Pydantic Settings requires JSON array format for list fields
ALLOWED_ORIGINS=["https://docforge.nstoug.com","http://localhost:5173"]

# === Database ===
POSTGRES_DB=docforge_db
POSTGRES_USER=docforge_user
POSTGRES_PASSWORD=change-me-strong-password
POSTGRES_HOST=db
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}

# === Redis ===
REDIS_URL=redis://redis:6379/0

# === LLM Providers ===
OPENROUTER_API_KEY=sk-or-...
# Optional direct provider keys (reserved for future fallback routing)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# === Rate Limiting (demo mode) ===
DEMO_RATE_LIMIT_PER_HOUR=10
DEMO_ALLOWED_MODELS=["google/gemini-2.0-flash-001","openai/gpt-4o-mini","openai/gpt-5.4-nano","meta-llama/llama-3.3-70b-instruct"]
```

---

## 10. Implementation Plan

### ✅ Stage 1: Project Initialization & Core Models

**Delivered**: Working skeleton — uv project, FastAPI app running, Pydantic models, async SQLAlchemy, Alembic environment, Docker Compose local dev stack, health endpoint.

Key files: `app/main.py`, `app/core/config.py`, `app/core/database.py`, `app/models/db.py`, `app/models/schemas.py`, `app/api/health.py`, `docker-compose.yml`.

**Quality gate passed**: `ruff check .` clean, `pyright .` clean, `GET /api/health` → 200.

---

### ✅ Stage 2: LangGraph Workflow Engine

**Delivered**: Full extraction pipeline — parse → chunk → extract → validate (with conditional retry loop up to 3 attempts) → merge. End-to-end: upload a document, get structured JSON back.

Key files: `app/workflows/state.py`, `app/workflows/nodes.py`, `app/workflows/graph.py`, `app/core/llm.py`, `app/services/extraction.py`.

Notable implementation details:
- `langchain-openrouter` (`ChatOpenRouter`) for all LLM calls — replaces the `ChatOpenAI` + custom base_url pattern
- `with_structured_output(schema)` requires a top-level `"title"` key — injected automatically if absent
- `RecursiveCharacterTextSplitter` with `chunk_size=4000`, `chunk_overlap=400`

**Quality gate passed**: Graph runs with a sample PDF + invoice schema, retries fire on intentionally invalid schema.

---

### ✅ Stage 3: API Endpoints & SSE Streaming

**Delivered**: Full REST API — schema CRUD, document upload (two-phase), SSE streaming, BYOK, demo rate limiting, built-in schema seeding, Alembic initial migration.

Key files: `app/api/schemas.py`, `app/api/documents.py`, `app/core/security.py`, `app/core/redis.py`, `app/services/extraction.py`, `alembic/versions/0001_*.py`.

Notable implementation details:
- **Two-phase design**: `POST /extract` saves file + creates `pending` job; `GET /stream` triggers and streams execution
- **SSE background task**: `_run_extraction_task` runs in its own `asyncio.Task` with a separate DB session — survives client disconnect, always commits final state
- **Timezone**: `completed_at` is `TIMESTAMP WITHOUT TIME ZONE`; all datetime assignments use `datetime.now(UTC).replace(tzinfo=None)`
- **Rate limiting**: Redis INCR/EXPIRE per IP; `require_demo_access` reads form data via `request.form()` to avoid double-parse with `UploadFile`

**Quality gate passed**: 23/23 tests pass, `ruff` + `pyright` clean. End-to-end verified: invoice PDF → 5 SSE node events → `done` → `status=completed` in DB.

---

### ✅ Stage 4: React Frontend

**Delivered**: Full SPA wizard — document upload, schema + model selection, BYOK, real-time SSE node progress, structured results with JSON/table toggle.

Key files: `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/hooks/useSSE.ts`, all components, `frontend/Dockerfile`, `frontend/nginx.conf`.

Notable implementation details:
- **`useSSE` hook**: Wraps `EventSource`, yields typed `StreamEvent[]`, `SSEStatus` (`idle|connecting|streaming|done|error`), `error`, and `reset()`. `useRef` status guard prevents stale-closure races on transport errors.
- **`App.tsx` SSE→result transition**: `useEffect` + `resultFetchedRef` ensures `getResult()` fires exactly once when SSE reaches `done`, even under React 19 strict-mode double-invocation.
- **`ModelSelector`**: Implemented as a radio-group (not `<select>`) to avoid multiple `combobox` ARIA roles conflicting with `SchemaSelector` in tests.
- **Static imports**: All API client functions use static `import` (not dynamic `import()`) so `vi.spyOn` works correctly in Vitest.
- **`NoopEventSource` stub**: Added to `test/setup.ts` so jsdom tests don't throw `EventSource is not defined`.
- **Nginx SSE config**: `proxy_buffering off`, `proxy_http_version 1.1`, `Connection ''`, `proxy_read_timeout 300s` — required for SSE to flow through the reverse proxy.
- **`docker-compose.yml`**: Frontend service added on port 3000 (`3000:80`), depends on backend.

**Quality gate passed**: 16/16 frontend tests pass, `npm run lint` clean, `npm run build` produces 210KB bundle. Backend: 23/23 tests pass (unchanged).

---

### Stage 5: CI/CD + Production Infrastructure ✅ COMPLETE

**Goal**: Production-grade containers, GitHub Actions CI/CD pipeline, pre-commit hooks, live deployment, production hardening.

**Completed tasks**:
1. Created `docker-compose.prod.yml` — backend + frontend + db + redis; frontend joins `gateway_net` as `docforge-frontend`; resource limits on all containers
2. Created `.github/workflows/deploy.yml` — test → ARM64 build → GHCR push → SCP + SSH deploy (3-job pipeline, all actions SHA-pinned)
3. Created `.pre-commit-config.yaml` — ruff-format, ruff, pyright, trailing-whitespace, eof-fixer, no-commit-to-branch
4. Created GitHub repo `niXtou/docforge` (public); branch protection on `main`; Dependabot + secret scanning enabled
5. Created `niXtou/hetzner-vps-portfolio-infra` (private) — central gateway nginx owning ports 80/443, routing by domain across all VPS projects
6. Deployed to production: `docforge.nstoug.com` live, migrations applied, all health checks passing
7. Production hardening: uv version pinned, HSTS at Cloudflare edge + nginx, rate limiting (20 r/s general / 5 r/s API), SSL session caching, keepalive upstreams, `docker image prune` (safe on shared VPS), portfolio port 8000 binding removed

**Architecture note — gateway_net**:
DocForge does **not** own ports 80/443. The gateway nginx lives in `niXtou/hetzner-vps-portfolio-infra`. DocForge's frontend joins the shared `gateway_net` Docker network with alias `docforge-frontend`. Lifecycle: add a project → add an upstream + server block to vps-infra nginx.conf + deploy that project's stack.

**Quality gate**: `curl https://docforge.nstoug.com/api/health` → `{"status":"ok","database":"ok","version":"0.1.0"}`. All pre-commit hooks pass. GitHub Actions 3 green jobs on push to main.

---

### Stage 6: README & Portfolio Integration ✅ COMPLETE

**Goal**: Polished README, portfolio entry, full smoke test.

**Tasks**:
1. ~~**Cloudflare**: Add `docforge` A record (proxied) → VPS IP~~ ✅ Done
2. ~~**SSL**: Cloudflare Origin Certificate (`*.nstoug.com` wildcard)~~ ✅ Done
3. ~~**VPS setup**: deploy compose stack, run migrations~~ ✅ Done
4. ~~**Nginx gateway**: `docforge.nstoug.com` server block in hetzner-vps-portfolio-infra~~ ✅ Done
5. ~~**README.md**: Architecture diagram (Mermaid), quick start, API reference, demo GIF~~ ✅ Done
6. ~~**Portfolio integration**: Create DocForge project entry in Django Admin — link to live demo + GitHub repo; write brief case study (self-correcting loop, LangGraph choice, interesting challenge)~~ ✅ Done
7. ~~**Smoke test**: Full extraction flow on production URL~~ ✅ Done

**Quality gate**: Full browser flow on `docforge.nstoug.com`. Portfolio entry visible at `nstoug.com`.

---

## 11. Portfolio Integration

### Adding DocForge

Create a project entry in your portfolio's Django Admin:

| Field | Value |
|-------|-------|
| `title` | DocForge — AI Document Intelligence |
| `primary_link` | `https://github.com/niXtou/docforge` |
| `primary_link_type` | GITHUB |
| `secondary_link` | `https://docforge.nstoug.com` |
| Technologies | Python, FastAPI, LangGraph, Pydantic, Docker, React, TypeScript, PostgreSQL, Redis |

Write the description as a brief case study, not a feature list — focus on the self-correcting extraction loop, why LangGraph over plain LangChain agents, and one interesting production challenge solved.

### Scaling to More Projects

Each project follows the same pattern:
1. Separate GitHub repo
2. `{project}.nstoug.com` subdomain
3. Independent Docker Compose stack on same VPS
4. Portfolio entry via Django Admin
5. Cloudflare DNS record

Scales cleanly to 5–10 projects on a cax11. If RAM becomes constrained, upgrade to cax21 (4 vCPU, 8 GB, ~€8/month) — Docker Compose stacks migrate trivially.

---

## 12. Cost Projections

| Item | Monthly Cost |
|------|-------------|
| Hetzner cax11 (shared with portfolio) | €0 incremental |
| Cloudflare (free tier) | €0 |
| Domain (nstoug.com, existing) | €0 |
| OpenRouter API (demo, rate-limited) | €5–10 |
| GitHub (free tier) | €0 |
| **Total** | **~€5–10/month** |

---

## 13. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM API costs spiral | Redis rate limiter (10/hour/IP) + model whitelist for demo mode; BYOK for power users |
| SSE connection drops mid-extraction | Background task pattern — extraction continues and commits regardless of client state |
| VPS RAM pressure | Redis + Postgres are lightweight; `docker stats` for monitoring; upgrade to cax21 if needed |
| LangGraph breaking changes | Version pinned in `pyproject.toml`; `uv.lock` for reproducibility |
| Extraction quality poor | Self-correcting retry loop (max 3); Pydantic validation errors fed back to LLM as context |
| Scope creep | This document. Ship each stage, verify, then proceed. |

---

*This document is the single reference for all architectural and planning decisions. Update it as the project evolves.*
