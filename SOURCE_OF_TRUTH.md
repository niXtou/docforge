# DocForge — Source of Truth

> **Last updated**: 2026-03-16
> **Status**: Pre-development
> **Author**: nstoug
> **Live demo target**: `docforge.nstoug.com`
> **Repository**: `github.com/<your-username>/docforge` (private until launch, then public)

---

## 1. Project Overview

**DocForge** is an AI-powered document intelligence API and web application. Users upload documents (PDF, CSV, plain text), define or select extraction schemas, and receive structured, validated JSON data — powered by a self-correcting LangGraph agent workflow with Pydantic validation at every step.

### Why This Project Exists

1. **Portfolio proof**: Demonstrates production-grade AI engineering — not a wrapper around an API call, but a stateful, multi-step, self-correcting agent system with proper infrastructure.
2. **Skill development**: Hands-on practice with LangGraph, FastAPI, Pydantic v2, Docker, and modern Python tooling.
3. **Potential micro-SaaS seed**: Document extraction is a real paid problem. If the demo gains traction, it can evolve into a product.
4. **Freelance leverage**: A live demo at `docforge.nstoug.com` linked from your portfolio is concrete evidence of capability when pitching to clients.

### What Makes It Non-Trivial

- **Self-correcting extraction loop**: LangGraph graph with conditional retry edges — the LLM gets its own Pydantic validation errors fed back and retries (max 3 attempts). This is the pattern production AI systems use.
- **Multi-provider LLM routing**: OpenRouter as primary router, direct SDK fallbacks, and BYOK (Bring Your Own Key) toggle.
- **Real-time streaming**: SSE (Server-Sent Events) from LangGraph node transitions to the frontend — users see which step the agent is on.
- **Schema-driven extraction**: Users define Pydantic-compatible JSON schemas. The system dynamically constructs extraction prompts from these schemas.

---

## 2. Architecture

### 2.1 System Diagram (C4 Level 2)

```
┌──────────────────────────────────────────────────────────────────┐
│  Cloudflare (Proxied DNS, Full Strict SSL)                       │
│  docforge.nstoug.com → Hetzner VPS :443                          │
└──────────────┬───────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────┐
│  Hetzner VPS — cax11 (ARM64, 2 vCPU, 4 GB RAM)                  │
│  /root/docforge/                                                 │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Nginx (Alpine)                                             │ │
│  │  :443 TLS termination (Cloudflare Origin Cert)              │ │
│  │  /          → frontend (React static build)                 │ │
│  │  /api/*     → FastAPI backend :8000                         │ │
│  │  /docs      → FastAPI auto-generated OpenAPI                │ │
│  └──────┬──────────────┬───────────────────────────────────────┘ │
│         │              │                                         │
│  ┌──────▼──────┐  ┌───▼───────────────────────────────────┐     │
│  │  Frontend   │  │  Backend (FastAPI + Uvicorn)           │     │
│  │  React 19   │  │  :8000                                 │     │
│  │  Vite build │  │                                        │     │
│  │  served by  │  │  ┌─────────────────────────────┐       │     │
│  │  Nginx      │  │  │  LangGraph Workflow Engine   │       │     │
│  └─────────────┘  │  │                               │       │     │
│                   │  │  Parse → Chunk → Extract       │       │     │
│                   │  │                   │    ▲       │       │     │
│                   │  │                   ▼    │       │       │     │
│                   │  │             Validate ──┘       │       │     │
│                   │  │                   │            │       │     │
│                   │  │                   ▼            │       │     │
│                   │  │                Merge           │       │     │
│                   │  └─────────────────────────────┘       │     │
│                   │         │              │                │     │
│                   │    ┌────▼───┐    ┌────▼────┐          │     │
│                   │    │Postgres│    │  Redis   │          │     │
│                   │    │  :5432 │    │  :6379   │          │     │
│                   │    └────────┘    └─────────┘          │     │
│                   └────────────────────────────────────────┘     │
│                                         │                        │
│                                    ┌────▼──────────┐             │
│                                    │  OpenRouter    │             │
│                                    │  (or direct    │             │
│                                    │   provider)    │             │
│                                    └───────────────┘             │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Network & DNS Configuration

| Record | Type | Content | Proxy | Notes |
|--------|------|---------|-------|-------|
| `docforge` | A | `<VPS IP>` | Proxied 🟠 | Same pattern as `api.nstoug.com` |

**SSL**: Cloudflare Full (Strict) with Origin Certificate. Same cert can cover `*.nstoug.com` if you use a wildcard, or generate a separate origin cert for `docforge.nstoug.com`.

**Nginx routing** (production): Single Nginx container handles both portfolio (`api.nstoug.com`) and DocForge (`docforge.nstoug.com`) via separate `server` blocks — OR each project runs its own Nginx in its own Compose stack listening on different host ports, with a shared outer Nginx routing by `server_name`. The second pattern is cleaner for independent projects.

**Recommended multi-project pattern**:
```
/root/
├── portfolio/          # existing — docker-compose.prod.yml, nginx on host port 8080
├── docforge/           # new — docker-compose.prod.yml, nginx on host port 8081
└── gateway/            # NEW — lightweight Nginx routing by server_name
    ├── docker-compose.yml
    └── nginx.conf      # server blocks for api.nstoug.com → :8080, docforge.nstoug.com → :8081
```

This gateway pattern means each project is fully self-contained and can be started/stopped independently. Adding a new project demo is: add a folder, add a server block to the gateway, add a Cloudflare DNS record.

> **NOTE**: You can start without the gateway — just expose DocForge Nginx directly on :443 with its own origin cert. Refactor to gateway pattern later when you have 3+ projects.

### 2.3 LangGraph Workflow (Core Logic)

This is the intellectual center of the project. Understand this fully before building.

```
                    ┌─────────┐
                    │  START   │
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  parse  │  ← Detect file type, extract raw text
                    │         │    (LangChain document loaders: PDF, CSV, TXT)
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  chunk  │  ← Split text into processable segments
                    │         │    (RecursiveCharacterTextSplitter or semantic)
                    └────┬────┘
                         │
                    ┌────▼─────┐
                    │ extract  │  ← LLM call: prompt + schema → structured output
                    │          │    Uses .with_structured_output(PydanticModel)
                    └────┬─────┘
                         │
                    ┌────▼──────┐
                    │ validate  │  ← Pydantic validation + custom business rules
                    │           │    Returns errors list or passes
                    └────┬──────┘
                         │
                    ┌────▼────┐        ┌───────────┐
                    │  route  │───No──▶│  retry    │
                    │ valid?  │        │ (feed     │
                    └────┬────┘        │  errors   │
                         │Yes          │  to LLM)  │
                         │             └─────┬─────┘
                         │                   │
                         │             (max 3 retries,
                         │              then fail gracefully)
                         │                   │
                    ┌────▼────┐              │
                    │  merge  │◀─────────────┘
                    │         │  ← Combine chunk-level extractions
                    └────┬────┘    Deduplicate, resolve conflicts
                         │
                    ┌────▼────┐
                    │   END   │  → Final ExtractionResult
                    └─────────┘
```

**Graph state** (Pydantic BaseModel):
```python
class WorkflowState(BaseModel):
    """Central state object flowing through the LangGraph graph."""
    # Input
    document_id: str
    raw_content: str = ""
    file_type: str = ""
    schema_definition: dict  # JSON Schema from user

    # Processing
    chunks: list[str] = []
    current_chunk_index: int = 0
    chunk_extractions: list[dict] = []

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    last_validation_errors: list[str] = []

    # Output
    final_result: dict | None = None
    status: str = "pending"  # pending | processing | completed | failed
    messages: list[str] = []  # Human-readable progress log
```

**🧠 LEARNING CHECKPOINT — LangGraph Fundamentals**:
Before building the workflow, complete these in order:
1. Read the [LangGraph overview docs](https://docs.langchain.com/oss/python/langgraph/overview) (30 min)
2. Build the "hello world" graph from the docs by hand — don't let AI generate it (20 min)
3. Understand `StateGraph`, `add_node`, `add_edge`, `add_conditional_edges` (20 min)
4. Build a minimal 3-node graph yourself: input → process → output (30 min)
5. Add a conditional retry edge yourself (30 min)
6. Only THEN let AI help you build the full DocForge workflow

---

## 3. Tech Stack (Final)

| Layer | Choice | Version | Rationale |
|-------|--------|---------|-----------|
| Language | Python | 3.12 | Stable across full dependency tree |
| Package manager | uv | latest | Modern standard, replaces pip/poetry/pipenv |
| API framework | FastAPI | 0.115+ | Native Pydantic, async-first, auto OpenAPI docs |
| Data validation | Pydantic | v2 (2.x) | State schemas, API models, extraction schemas, LLM structured output |
| Agent orchestration | LangGraph | 1.x | Production-grade stateful agent workflows |
| LLM integrations | LangChain | 0.3.x | Document loaders, text splitters, model wrappers |
| LLM routing | OpenRouter | — | Single API key → Claude, GPT-4o, Gemini, open-source |
| LLM fallback | Direct SDKs | — | anthropic, openai, google-genai (when OpenRouter lacks features) |
| Database | PostgreSQL | 15 | Stores schemas, documents, results |
| Cache / queue | Redis | 7 | Response caching, rate limiting, task state |
| ORM | SQLAlchemy | 2.x (async) | Async session support, Alembic migrations |
| Migrations | Alembic | latest | Schema versioning |
| Frontend | React 19 | + Vite + TS + Tailwind | Modern SPA with real-time SSE streaming |
| Containerization | Docker Compose | — | Multi-stage builds, health checks |
| CI/CD | GitHub Actions | — | SSH deploy to Hetzner (mirrors portfolio pattern) |
| DNS/SSL | Cloudflare | Full Strict | Origin certificates, WAF |
| Linting/Formatting | Ruff | latest | Replaces black + isort + flake8 (2026 standard) |
| Type checking | Pyright | latest | Stricter than mypy, better Pydantic v2 support |
| Testing | Pytest | + httpx + pytest-asyncio | Async test support for FastAPI + LangGraph |

### Python Dependencies (pyproject.toml core)

```toml
[project]
name = "docforge"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    # API
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "python-multipart>=0.0.9",    # file uploads

    # Data
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29.0",            # async Postgres driver
    "alembic>=1.13.0",
    "redis>=5.0.0",

    # AI / LLM
    "langgraph>=1.0.0",
    "langchain>=0.3.0",
    "langchain-openai>=0.2.0",
    "langchain-anthropic>=0.3.0",
    "langchain-google-genai>=2.0.0",
    "langchain-community>=0.3.0",  # document loaders

    # Validation & Config
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",

    # Document Processing
    "pypdf>=4.0.0",               # PDF text extraction
    "python-docx>=1.0.0",         # DOCX support (future)

    # Utilities
    "httpx>=0.27.0",              # async HTTP client (OpenRouter)
    "sse-starlette>=2.0.0",       # SSE streaming
    "python-jose[cryptography]>=3.3.0",  # JWT for API keys
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",              # TestClient
    "ruff>=0.6.0",
    "pyright>=1.1.380",
    "pre-commit>=3.8.0",
]
```

---

## 4. Repository Structure

```
docforge/
├── .github/
│   └── workflows/
│       └── deploy.yml              # CI/CD: test → build → deploy
├── AGENTS.md                       # AI collaboration guide
├── SOURCE_OF_TRUTH.md              # This document
├── README.md                       # Public-facing project README
├── LICENSE                         # MIT
├── .gitignore
├── .pre-commit-config.yaml
├── docker-compose.yml              # Local development
├── docker-compose.prod.yml         # Production
├── .env.example                    # Template for required env vars
│
├── backend/
│   ├── Dockerfile                  # Multi-stage: uv install → runtime
│   ├── pyproject.toml              # uv-managed dependencies
│   ├── uv.lock                     # Lockfile
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app factory + lifespan
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── router.py           # Main API router
│   │   │   ├── schemas.py          # Route handlers for schemas CRUD
│   │   │   ├── documents.py        # Route handlers for document upload + extraction
│   │   │   ├── health.py           # Health check endpoint
│   │   │   └── deps.py             # FastAPI dependencies (DB session, auth, etc.)
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py           # Pydantic Settings (env-based config)
│   │   │   ├── database.py         # Async SQLAlchemy engine + session
│   │   │   ├── security.py         # API key validation, BYOK logic
│   │   │   └── llm.py              # LLM provider factory (OpenRouter / direct / BYOK)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── db.py               # SQLAlchemy ORM models
│   │   │   └── schemas.py          # Pydantic response/request models
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── document.py         # Document processing service
│   │   │   └── extraction.py       # Schema-to-prompt construction
│   │   └── workflows/
│   │       ├── __init__.py
│   │       ├── graph.py            # Main LangGraph workflow definition
│   │       ├── nodes.py            # Individual node functions
│   │       └── state.py            # WorkflowState Pydantic model
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py             # Fixtures: async DB, mock LLM, test client
│       ├── test_api.py             # Endpoint tests
│       ├── test_workflow.py        # LangGraph workflow tests (mocked LLM)
│       └── test_models.py          # Pydantic model validation tests
│
├── frontend/
│   ├── Dockerfile                  # Multi-stage: npm build → nginx
│   ├── nginx.conf                  # Serves static build
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   └── client.ts           # API client + SSE consumer
│       ├── components/
│       │   ├── DocumentUpload.tsx
│       │   ├── SchemaSelector.tsx
│       │   ├── ExtractionProgress.tsx   # Real-time SSE visualization
│       │   ├── ResultsViewer.tsx
│       │   ├── ApiKeyInput.tsx          # BYOK toggle
│       │   └── Layout.tsx
│       ├── hooks/
│       │   └── useSSE.ts           # Custom SSE hook
│       ├── types/
│       │   └── index.ts
│       └── lib/
│           └── utils.ts
│
└── nginx/                          # Production outer proxy
    └── nginx.conf                  # server_name docforge.nstoug.com
```

---

## 5. API Specification

### Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/health` | Health check (DB + Redis connectivity) | None |
| `GET` | `/api/schemas` | List available extraction schemas | None |
| `GET` | `/api/schemas/{id}` | Get schema detail | None |
| `POST` | `/api/schemas` | Create custom extraction schema | API key |
| `POST` | `/api/extract` | Upload document + select schema → start extraction | API key or BYOK |
| `GET` | `/api/extract/{job_id}/stream` | SSE stream of extraction progress | None (job_id is secret) |
| `GET` | `/api/extract/{job_id}/result` | Final extraction result | None (job_id is secret) |
| `GET` | `/docs` | OpenAPI / Swagger UI (auto-generated) | None |

### Key Pydantic Models

```python
# --- Request Models ---

class SchemaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="")
    json_schema: dict  # JSON Schema defining the extraction target
    # Example: {"type": "object", "properties": {"vendor": {"type": "string"}, ...}}

class ExtractionRequest(BaseModel):
    schema_id: int
    model: str = Field(default="anthropic/claude-sonnet-4-20250514")  # OpenRouter model string
    api_key: str | None = None  # BYOK — if None, use server key (rate-limited)

# --- Response Models ---

class ExtractionJob(BaseModel):
    job_id: str  # UUID
    status: str  # pending | processing | completed | failed
    schema_name: str
    created_at: datetime

class ExtractionResult(BaseModel):
    job_id: str
    status: str
    data: dict | None  # The structured extraction result
    validation_passed: bool
    retries_used: int
    model_used: str
    processing_time_ms: int
    chunks_processed: int

class StreamEvent(BaseModel):
    """SSE event payload."""
    event: str  # node_started | node_completed | retry | error | done
    node: str | None = None
    message: str
    timestamp: datetime
    data: dict | None = None  # Optional payload (e.g., partial results)
```

### Pre-built Extraction Schemas (Demo)

Ship with 3 schemas that showcase different complexity levels:

1. **Invoice** — `vendor`, `invoice_number`, `date`, `line_items[]` (nested: description, qty, unit_price, total), `subtotal`, `tax`, `total`
2. **Resume / CV** — `name`, `email`, `phone`, `summary`, `experience[]` (nested: title, company, dates, description), `education[]`, `skills[]`
3. **Research Paper** — `title`, `authors[]`, `abstract`, `keywords[]`, `methodology`, `findings`, `references_count`

---

## 6. Data Models (Database)

### SQLAlchemy ORM

```python
class ExtractionSchema(Base):
    __tablename__ = "extraction_schemas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    json_schema: Mapped[dict] = mapped_column(JSON)  # The Pydantic-compatible schema
    is_builtin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    jobs: Mapped[list["ExtractionJob"]] = relationship(back_populates="schema")


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    schema_id: Mapped[int] = mapped_column(ForeignKey("extraction_schemas.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    original_filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(10))
    model_used: Mapped[str] = mapped_column(String(100))
    result_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_passed: Mapped[bool | None] = mapped_column(nullable=True)
    retries_used: Mapped[int] = mapped_column(default=0)
    processing_time_ms: Mapped[int | None] = mapped_column(nullable=True)
    chunks_processed: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    schema: Mapped["ExtractionSchema"] = relationship(back_populates="jobs")
```

---

## 7. LLM Provider Architecture

### OpenRouter-first pattern

```python
# app/core/llm.py

from langchain_openai import ChatOpenAI

def get_llm(
    model: str = "anthropic/claude-sonnet-4-20250514",
    api_key: str | None = None,  # BYOK
    temperature: float = 0.0,
) -> ChatOpenAI:
    """
    Factory for LLM instances.

    Uses OpenRouter as a unified gateway. OpenRouter accepts the same
    API format as OpenAI, so we use ChatOpenAI with a custom base_url.

    If api_key is provided (BYOK), use it. Otherwise, use server key.
    """
    effective_key = api_key or settings.OPENROUTER_API_KEY

    return ChatOpenAI(
        model=model,
        api_key=effective_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
        default_headers={
            "HTTP-Referer": "https://docforge.nstoug.com",
            "X-Title": "DocForge",
        },
    )
```

**Why this works**: OpenRouter exposes an OpenAI-compatible API. LangChain's `ChatOpenAI` works with any OpenAI-compatible endpoint via `base_url`. This means we get Claude, GPT-4o, Gemini, Llama, Mistral, etc. through one interface — no provider-specific code paths.

**BYOK flow**: The frontend has a toggle. If the user provides their own OpenRouter API key, it's passed per-request. If not, the server key is used with aggressive rate limiting (Redis-based, e.g., 10 extractions/hour per IP).

### Rate Limiting (demo protection)

```python
# Redis-based rate limiter for demo mode
DEMO_RATE_LIMIT = 10  # extractions per hour per IP
DEMO_MODEL_WHITELIST = [
    "anthropic/claude-sonnet-4-20250514",  # cost-effective
    "google/gemini-2.0-flash",       # cheap
    "openai/gpt-4o-mini",            # cheap
]
```

---

## 8. Deployment Configuration

### Docker Compose (Production)

```yaml
# docker-compose.prod.yml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    image: ghcr.io/<your-username>/docforge-backend:latest
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/api/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    volumes:
      - docforge_pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - docforge_redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  nginx:
    image: nginx:1.25-alpine
    ports:
      - "8081:443"    # Different host port than portfolio (8080)
      - "8082:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro   # Cloudflare Origin Cert
      - frontend_build:/usr/share/nginx/html:ro
    depends_on:
      - backend
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    volumes:
      - frontend_build:/app/dist

volumes:
  docforge_pgdata:
  docforge_redisdata:
  frontend_build:
```

### Backend Dockerfile (Multi-stage with uv)

```dockerfile
# Stage 1: Build
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

COPY app/ app/
COPY alembic.ini alembic/ ./

# Stage 2: Runtime
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

### Frontend Dockerfile (Multi-stage)

```dockerfile
# Stage 1: Build
FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Output
FROM alpine:latest AS output
COPY --from=builder /app/dist /app/dist
```

### CI/CD (.github/workflows/deploy.yml)

Mirrors the portfolio pattern:
1. **Test job**: Run pytest (backend) + vitest (frontend)
2. **Build job**: Multi-arch Docker build (ARM64), push to GHCR
3. **Deploy job**: SSH into VPS, pull images, run migrations, restart

---

## 9. Environment Variables

```env
# .env.example

# === Django / FastAPI ===
SECRET_KEY=change-me-to-random-string
DEBUG=False
ALLOWED_ORIGINS=https://docforge.nstoug.com

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
# Optional direct provider keys (fallback)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# === Rate Limiting (demo) ===
DEMO_RATE_LIMIT_PER_HOUR=10
DEMO_ALLOWED_MODELS=anthropic/claude-sonnet-4-20250514,google/gemini-2.0-flash,openai/gpt-4o-mini
```

---

## 10. Implementation Plan (Stage-by-Stage)

Each stage has clear deliverables, learning checkpoints, and quality gates. Estimated total: 36–48 hours of focused work across 3–4 days.

---

### Stage 1: Project Initialization & Core Models (4–5 hours)

**Goal**: Working project skeleton — `uv` project, FastAPI app running, Pydantic models defined, database connected.

**Tasks**:
1. Create GitHub repo (private), clone locally
2. Initialize Python project with `uv init`
3. Configure `pyproject.toml` with all dependencies
4. Set up project directory structure (as defined in Section 4)
5. Define Pydantic models in `app/models/schemas.py`:
   - `SchemaCreate`, `ExtractionRequest`, `ExtractionJob`, `ExtractionResult`, `StreamEvent`
6. Define SQLAlchemy models in `app/models/db.py`:
   - `ExtractionSchema`, `ExtractionJob`
7. Set up `app/core/config.py` with Pydantic Settings
8. Set up `app/core/database.py` with async SQLAlchemy
9. Create Alembic migration environment + initial migration
10. Create `app/main.py` — FastAPI app with lifespan (DB init)
11. Create `app/api/health.py` — basic health endpoint
12. Set up `docker-compose.yml` for local dev (backend + postgres + redis)
13. Verify: `docker compose up` → `curl localhost:8000/api/health` → 200 OK

**🧠 LEARNING CHECKPOINT**:
- Write the Pydantic models by hand. Understand `Field()`, `model_config`, validators.
- Write the SQLAlchemy async setup by hand. Understand `create_async_engine`, `async_session`.
- Use AI for boilerplate only (Dockerfile, docker-compose, alembic config).

**Quality gate**: `ruff check .` passes, `pyright .` passes, health endpoint returns JSON.

---

### Stage 2: LangGraph Workflow Engine (8–10 hours)

**Goal**: Working extraction pipeline — upload a document, get structured JSON back. This is the core of the project.

**Tasks**:
1. Define `WorkflowState` in `app/workflows/state.py` (Pydantic BaseModel)
2. Implement `get_llm()` factory in `app/core/llm.py`
3. Build individual node functions in `app/workflows/nodes.py`:
   - `parse_document()` — use LangChain `PyPDFLoader`, `CSVLoader`, `TextLoader`
   - `chunk_text()` — `RecursiveCharacterTextSplitter` (configurable chunk size)
   - `extract_structured()` — construct prompt from schema + chunk, call LLM with `.with_structured_output()`
   - `validate_extraction()` — run Pydantic validation, collect errors
   - `merge_extractions()` — combine chunk-level results, deduplicate
4. Assemble the graph in `app/workflows/graph.py`:
   - `StateGraph(WorkflowState)`
   - Wire nodes with edges
   - Add conditional edge: validate → retry (if errors and retries < max) or merge (if valid)
   - Compile graph
5. Implement `app/services/extraction.py` — orchestrates: create DB job → run graph → update DB
6. Test end-to-end: hardcoded invoice PDF → structured JSON

**🧠 LEARNING CHECKPOINT — This is the most important stage for learning**:
- Build the graph incrementally. Start with just parse → extract → END (no chunking, no retry).
- Add chunking. Test.
- Add validation + conditional retry edge. Test.
- Add merge. Test.
- Understand WHY each node exists before coding it.
- Write `nodes.py` functions by hand first, then refine with AI.
- Use AI for: prompt engineering (the extraction prompt template), LangChain loader boilerplate.

**Quality gate**: Run the graph with a sample PDF and a hardcoded invoice schema. Get valid JSON back. Retries fire when you intentionally corrupt the schema.

---

### Stage 3: API Endpoints & SSE Streaming (5–6 hours)

**Goal**: Full REST API — schemas CRUD, document upload, extraction trigger, real-time progress streaming.

**Tasks**:
1. Implement `app/api/schemas.py`:
   - `GET /api/schemas` — list (with builtin flag)
   - `GET /api/schemas/{id}` — detail
   - `POST /api/schemas` — create custom
2. Implement `app/api/documents.py`:
   - `POST /api/extract` — file upload (multipart) + schema selection → create job → start extraction
   - `GET /api/extract/{job_id}/stream` — SSE endpoint
   - `GET /api/extract/{job_id}/result` — final result
3. Implement SSE streaming:
   - Hook into LangGraph's streaming API to emit events per node
   - Use `sse-starlette` for SSE response
4. Implement BYOK + rate limiting in `app/core/security.py`:
   - Check for user-provided API key in request header
   - If no key, apply Redis-based rate limit
5. Seed pre-built schemas (invoice, resume, research paper)
6. Test all endpoints with `httpx` / curl

**🧠 LEARNING CHECKPOINT**:
- Understand SSE (Server-Sent Events) — it's simpler than WebSockets, one-directional, perfect for progress updates.
- Implement the SSE endpoint by hand. AI can help with the LangGraph streaming integration.
- Understand FastAPI's dependency injection (`Depends()`) for auth/rate-limiting.

**Quality gate**: Upload a PDF via curl with multipart form, connect to SSE stream, see node-by-node progress, get final result from result endpoint.

---

### Stage 4: React Frontend (6–8 hours)

**Goal**: Clean, functional UI for document upload, schema selection, real-time progress, and results display.

**Tasks**:
1. Scaffold: `npm create vite@latest frontend -- --template react-ts`
2. Install + configure: Tailwind CSS, necessary dependencies
3. Build components:
   - `Layout.tsx` — header, footer, dark/light mode
   - `DocumentUpload.tsx` — drag-and-drop file upload
   - `SchemaSelector.tsx` — dropdown of available schemas + "view schema" modal
   - `ApiKeyInput.tsx` — BYOK toggle with key input field
   - `ExtractionProgress.tsx` — real-time visualization consuming SSE stream
     - Show which node is active (parse → chunk → extract → validate → merge)
     - Show retry attempts if any
     - Animated step indicators
   - `ResultsViewer.tsx` — structured JSON viewer + table view toggle
4. Implement `useSSE.ts` custom hook for SSE consumption
5. Implement API client in `api/client.ts`
6. Wire everything together in `App.tsx`
7. Frontend Dockerfile (multi-stage build)
8. Add frontend to docker-compose

**🧠 LEARNING CHECKPOINT**:
- The SSE consumer (`useSSE.ts`) is a good thing to write by hand — it's simple and teaches you EventSource API.
- Let AI generate the UI components (layout, styling, drag-and-drop). Focus your energy on the data flow.

**Quality gate**: Full flow works in browser — upload file → see progress → see results. Responsive on mobile.

---

### Stage 5: Docker, Testing & Quality (5–6 hours)

**Goal**: Production-ready containers, test suite, CI-ready.

**Tasks**:
1. Finalize `docker-compose.yml` (local) and `docker-compose.prod.yml`
2. Multi-stage Dockerfiles for backend + frontend
3. Write tests:
   - `test_models.py` — Pydantic model validation (edge cases, bad input)
   - `test_workflow.py` — LangGraph workflow with mocked LLM responses
   - `test_api.py` — endpoint tests with `httpx.AsyncClient`
4. Configure `pyproject.toml` for pytest + ruff + pyright
5. Set up `.pre-commit-config.yaml` (ruff, pyright, trailing whitespace)
6. Set up GitHub Actions: test job (Python 3.12 + Node 22)
7. Verify: `docker compose up --build` from clean state works end-to-end

**🧠 LEARNING CHECKPOINT**:
- Write the workflow tests by hand — mocking LLM responses teaches you how LangGraph state flows.
- AI can generate API test boilerplate and Dockerfile optimization.

**Quality gate**: All tests pass. `ruff check .` clean. `pyright .` clean. `docker compose build` succeeds.

---

### Stage 6: Deployment & Documentation (4–5 hours)

**Goal**: Live at `docforge.nstoug.com`, polished README, portfolio integration.

**Tasks**:
1. **Cloudflare**: Add `docforge` A record (proxied) pointing to VPS IP
2. **SSL**: Generate Cloudflare Origin Certificate for `docforge.nstoug.com` (or use wildcard `*.nstoug.com`)
3. **VPS setup**:
   - `mkdir -p /root/docforge`
   - Copy `docker-compose.prod.yml`, `.env`, `nginx/` configs
   - Pull images, run migrations, start services
4. **Nginx config**: TLS termination, proxy to backend, serve frontend
5. **GitHub Actions deploy workflow**: mirrors portfolio pattern
6. **README.md**: Architecture diagram, quick start, API docs link, demo GIF/screenshots
7. **Portfolio integration**:
   - Add DocForge as a Project in your portfolio's Django admin
   - Link to `docforge.nstoug.com` as live demo
   - Link to GitHub repo
   - Add a brief case study / write-up using your Headless CMS
8. **Smoke test**: Full extraction flow on production

**Quality gate**: `curl https://docforge.nstoug.com/api/health` returns 200. Full flow works in browser on production domain. README has architecture diagram and quick start.

---

## 11. Portfolio Integration Strategy

### Current Setup (from your SOURCE_OF_TRUTH.md)

Your portfolio at `nstoug.com` uses a Headless CMS (Django Admin → Markdown/HTML/LaTeX → React renderer). Projects are stored as database entries with `content`, `primary_link`, `video_url`, etc.

### Adding DocForge

1. **Django Admin**: Create a new Project entry:
   - `title`: "DocForge — AI Document Intelligence"
   - `content`: Markdown case study (architecture decisions, challenges, what you learned)
   - `primary_link`: `https://github.com/<user>/docforge`
   - `primary_link_type`: GITHUB
   - `secondary_link`: `https://docforge.nstoug.com`
   - `is_github_repo_private`: False (after launch)
   - Technologies M2M: Python, FastAPI, LangGraph, Pydantic, Docker, React, TypeScript, PostgreSQL, Redis

2. **Content strategy**: Write the project description as a brief case study, not a feature list. Focus on: the self-correcting extraction loop, why you chose the stack, and one interesting technical challenge you solved.

### Future Projects Pattern

Every future project follows the same pattern:
1. Separate GitHub repo
2. `{project}.nstoug.com` subdomain on same VPS
3. Independent Docker Compose stack
4. Portfolio entry via Django Admin
5. Cloudflare DNS record (one-time, 30 seconds)

This scales cleanly to 5–10 projects. If you outgrow the cax11, upgrade to cax21 (4 vCPU, 8 GB, ~€8/month) — Docker Compose stacks migrate trivially.

---

## 12. Cost Projections

| Item | Monthly Cost |
|------|-------------|
| Hetzner cax11 (shared with portfolio) | €0 incremental |
| Cloudflare (free tier) | €0 |
| Domain (nstoug.com, existing) | €0 |
| OpenRouter API (demo, rate-limited) | €5–10 |
| GitHub (free tier, public repo) | €0 |
| **Total** | **~€5–10/month** |

---

## 13. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM API costs spiral (abuse) | Redis rate limiter + model whitelist for demo mode |
| VPS runs out of RAM | Redis + Postgres are lightweight; monitor with `docker stats`; upgrade to cax21 if needed |
| LangGraph breaking changes | Pin to specific version in `pyproject.toml`; use `uv.lock` |
| Extraction quality poor | Self-correcting retry loop; good prompt engineering; model selection |
| Scope creep | This document. Stick to the stages. Ship MVP, iterate. |

---

*End of Source of Truth. This document is the single reference for all architectural and planning decisions. Update it as the project evolves.*
