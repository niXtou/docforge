# AGENTS.md — AI Collaboration Guide for DocForge

> **Purpose**: This document defines how to work with AI coding tools efficiently during DocForge development. It covers which tools to use for what, prompting strategies, cost optimization, context management, and learning-first workflow patterns.
>
> **Philosophy**: AI accelerates execution, but you drive architecture and understanding. The goal is to ship fast AND build durable skills. Every section marks what to write by hand vs. what to delegate to AI.

---

## 1. Tool Roster & Roles

You have four AI coding tools. Each has a sweet spot — using the wrong tool for the wrong task wastes time and money.

### Claude Code (CLI) — **Primary development driver**

**Use for**: Multi-file code generation, refactoring across files, running tests, debugging, git operations, Docker troubleshooting, and any task that benefits from seeing your full project context.

**Why it's primary**: Claude Code can read your entire repo, run commands, edit files, and iterate. It has the deepest context window and the best code generation quality for Python.

**When to use**:
- "Implement the `parse_document` node in `nodes.py` and wire it into `graph.py`"
- "Run the tests and fix any failures"
- "Set up the Alembic migration for the new models"
- "Debug why the SSE stream disconnects after 30 seconds"
- Refactoring that touches 3+ files

**Cost**: Included in your subscription. Use liberally.

**Tips**:
- Keep `AGENTS.md` and `SOURCE_OF_TRUTH.md` in the repo root — Claude Code reads them automatically.
- Use `/compact` when context gets large.
- Provide clear, scoped instructions. Bad: "Build the backend." Good: "Implement `app/workflows/nodes.py` — the `extract_structured` function. It should take `WorkflowState`, call the LLM using `get_llm()` with `.with_structured_output()`, and return the updated state. Refer to the schema in SOURCE_OF_TRUTH.md Section 2.3."

### OpenCode + OpenRouter — **Secondary development / exploration**

**Use for**: Same tasks as Claude Code but when you want to use a different model (e.g., GPT-4.1 for a second opinion, or a cheaper model for simple tasks). Also good for experimenting with different coding approaches.

**When to use**:
- Getting a second opinion on architecture decisions
- Simple file generation where Claude Code's subscription feels heavy
- Testing how different models approach the same problem
- Generating boilerplate (Dockerfiles, configs, CI/CD)

**Cost model (OpenRouter)**:
| Model | Input/1M tokens | Output/1M tokens | Use for |
|-------|---------|---------|---------|
| `google/gemini-2.0-flash-001` | $0.10 | $0.40 | Boilerplate, simple edits, explanations |
| `anthropic/claude-sonnet-4-20250514` | $3.00 | $15.00 | Complex code generation, debugging |
| `openai/gpt-4.1` | $2.00 | $8.00 | Second opinions, alternative approaches |
| `openai/gpt-4.1-mini` | $0.40 | $1.60 | Documentation, simple code |

**Cost optimization**: Use Gemini Flash or GPT-4.1-mini for anything that doesn't require deep reasoning. Switch to Claude Sonnet or GPT-4.1 only for complex multi-file changes or tricky bugs.

### ChatGPT / Claude Web UI — **Planning, learning, and debugging**

**Use for**: Conceptual questions, learning LangGraph concepts, debugging approaches, code review, and planning. NOT for writing code that goes directly into files.

**When to use**:
- "Explain how LangGraph conditional edges work with a simple example"
- "Review this `graph.py` I wrote — what's wrong with my state management?"
- "What's the best way to handle SSE disconnections in FastAPI?"
- "Compare these two approaches to chunking for structured extraction"
- Planning prompts before delegating to Claude Code

**Cost**: Included in subscriptions. Use freely.

**Tips**:
- Paste your `WorkflowState` model and ask conceptual questions about it.
- Use Claude web UI for Anthropic-specific questions (Claude API, Pydantic AI integration).
- Use ChatGPT for OpenAI-ecosystem questions and general coding patterns.

### GitHub Copilot — **Inline autocomplete only**

**Use for**: Line-by-line autocomplete while you're actively coding in your editor. Tab-completion for obvious patterns.

**When NOT to use**: Don't rely on Copilot for multi-file changes, architecture decisions, or anything requiring project-wide context. It doesn't see your full repo the way Claude Code does.

**Tips**:
- Keep it enabled for speed on boilerplate (imports, type hints, docstrings).
- Disable Copilot Chat if you find it conflicting with Claude Code's suggestions.
- Copilot is strongest for React/TypeScript components and pytest fixtures.

---

## 2. Workflow: The Build Loop

For every implementation task, follow this loop:

```
┌─────────────────────────────────────────────────┐
│  1. UNDERSTAND (you + web UI)                    │
│     Read docs, ask conceptual questions.         │
│     Don't write code yet.                        │
├─────────────────────────────────────────────────┤
│  2. SKETCH (you, by hand)                        │
│     Write pseudocode or a minimal version.       │
│     This is where learning happens.              │
├─────────────────────────────────────────────────┤
│  3. IMPLEMENT (you + Claude Code / OpenCode)     │
│     Expand the sketch into full code.            │
│     AI fills in boilerplate and handles edge     │
│     cases you identified in step 2.              │
├─────────────────────────────────────────────────┤
│  4. VERIFY (you + AI)                            │
│     Run tests, run linter, run type checker.     │
│     If it fails, debug with AI assistance.       │
├─────────────────────────────────────────────────┤
│  5. REVIEW (you)                                 │
│     Read the final code. Understand every line.  │
│     If you can't explain it, rewrite it.         │
└─────────────────────────────────────────────────┘
```

**The cardinal rule**: Never commit code you don't understand. If AI generates something and you're not sure how it works, ask the web UI to explain it before moving on.

---

## 3. Context Management Strategy

AI tools work best with focused, relevant context. Here's how to manage it:

### Repository-level context files

These files live in your repo root. Claude Code and OpenCode read them automatically:

| File | Purpose | When to update |
|------|---------|----------------|
| `AGENTS.md` | This file — AI collaboration instructions | Rarely (start of project) |
| `SOURCE_OF_TRUTH.md` | Architecture, models, API spec, plan | After each stage completion |
| `README.md` | Public project description | After Stage 6 |
| `.cursorrules` / `.claude` | Tool-specific config (if needed) | As needed |

### Prompt templates for common tasks

Save these and reuse them — they dramatically improve output quality.

**Template: Implement a new node**
```
Implement the `{node_name}` function in `app/workflows/nodes.py`.

Context:
- This is a LangGraph node that receives and returns `WorkflowState` (defined in `app/workflows/state.py`)
- Refer to SOURCE_OF_TRUTH.md Section 2.3 for the workflow architecture
- Use async/await throughout

Requirements:
- {specific requirements}
- Add proper error handling (update state.messages on failure)
- Add type hints for all parameters and return values
- Follow the pattern established by existing nodes in the file

Do NOT modify any other files. I'll wire this into the graph separately.
```

**Template: Implement a FastAPI endpoint**
```
Implement the `{endpoint_description}` endpoint in `app/api/{file}.py`.

Context:
- Refer to SOURCE_OF_TRUTH.md Section 5 for the API specification
- Use the Pydantic models from `app/models/schemas.py`
- Use async SQLAlchemy session from `app/api/deps.py`

Requirements:
- {specific requirements}
- Proper HTTP status codes (201 for create, 404 for not found, etc.)
- Input validation via Pydantic (FastAPI handles this automatically)
- Docstring that appears in OpenAPI/Swagger

Include the test in `tests/test_api.py` as well.
```

**Template: Debug a failure**
```
The following test/command is failing:

```
{error output}
```

Relevant files:
- {list files}

The expected behavior is: {description}
The actual behavior is: {description}

Diagnose the root cause and fix it. Explain what went wrong.
```

### Context window management

When working on a specific stage, tell your AI tool what's relevant:

```
I'm working on Stage 2 (LangGraph Workflow Engine) from SOURCE_OF_TRUTH.md.
The relevant files are:
- app/workflows/state.py (WorkflowState model)
- app/workflows/nodes.py (node functions)
- app/workflows/graph.py (graph assembly)
- app/core/llm.py (LLM factory)

Ignore the frontend, Docker, and CI/CD files for now.
```

This prevents the AI from trying to "help" by modifying unrelated files.

---

## 4. Stage-Specific AI Delegation Guide

### Stage 1: Project Initialization

| Task | Do yourself | Delegate to AI | Tool |
|------|-------------|----------------|------|
| `uv init`, project structure | ✅ | — | Terminal |
| `pyproject.toml` dependencies | — | ✅ (from SOT Section 3) | Claude Code |
| Pydantic models | ✅ Write first draft | Refine + add validators | Claude Code |
| SQLAlchemy models | ✅ Write by hand | — | — |
| Async DB setup | ✅ Understand the pattern | Generate boilerplate | Claude Code |
| Alembic config | — | ✅ | Claude Code |
| Docker Compose (local) | — | ✅ | Claude Code |
| Dockerfile | — | ✅ (from SOT Section 8) | Claude Code |
| FastAPI app factory | ✅ Write by hand | — | — |
| Health endpoint | ✅ (it's 10 lines) | — | — |

### Stage 2: LangGraph Workflow ⚠️ HIGHEST LEARNING VALUE

| Task | Do yourself | Delegate to AI | Tool |
|------|-------------|----------------|------|
| `WorkflowState` model | ✅ Write by hand | — | — |
| Read LangGraph docs | ✅ (30+ min) | — | Docs website |
| Build minimal 3-node graph | ✅ Write by hand | — | — |
| `parse_document` node | ✅ Write core logic | LangChain loader boilerplate | Claude Code |
| `chunk_text` node | ✅ Write by hand | — | — |
| `extract_structured` node | ✅ Write the structure | Prompt template text | ChatGPT/Claude UI |
| `validate_extraction` node | ✅ Write by hand | — | — |
| Conditional retry edge | ✅ Write by hand | — | — |
| `merge_extractions` node | ✅ Write core | Edge case handling | Claude Code |
| Graph assembly | ✅ Wire it yourself | — | — |
| `get_llm()` factory | — | ✅ | Claude Code |
| End-to-end test | ✅ Run and debug | Fix issues | Claude Code |

**Rationale**: This is where you build LangGraph muscle memory. If AI writes the graph, you learn nothing. Write it, break it, fix it, THEN use AI to polish.

### Stage 3: API & Streaming

| Task | Do yourself | Delegate to AI | Tool |
|------|-------------|----------------|------|
| Schemas CRUD endpoints | Understand pattern | ✅ Generate | Claude Code |
| Document upload endpoint | ✅ Write core | File handling boilerplate | Claude Code |
| SSE endpoint | ✅ Understand EventSource | Implementation | Claude Code |
| SSE + LangGraph integration | ✅ Design the event flow | Wiring code | Claude Code |
| BYOK security logic | ✅ Write by hand | — | — |
| Rate limiting (Redis) | — | ✅ | Claude Code |
| Seed schemas | — | ✅ (from SOT Section 5) | Claude Code |

### Stage 4: React Frontend

| Task | Do yourself | Delegate to AI | Tool |
|------|-------------|----------------|------|
| Vite + Tailwind scaffold | — | ✅ | Claude Code |
| `useSSE.ts` hook | ✅ Write by hand | — | — |
| API client | — | ✅ | Claude Code |
| Component layouts | — | ✅ | Claude Code |
| ExtractionProgress visualization | ✅ Design the UX | Implementation | Claude Code |
| ResultsViewer (JSON + table) | — | ✅ | Claude Code |
| Wiring components together | ✅ Understand data flow | — | — |
| Responsive / dark mode | — | ✅ | Claude Code |

### Stage 5: Docker, Testing, Quality

| Task | Do yourself | Delegate to AI | Tool |
|------|-------------|----------------|------|
| Production Docker Compose | — | ✅ (from SOT Section 8) | Claude Code |
| Workflow tests (mock LLM) | ✅ Write yourself | — | — |
| API endpoint tests | ✅ Write first few | Generate remaining | Claude Code |
| Pydantic model tests | ✅ Write by hand | — | — |
| pre-commit config | — | ✅ | Claude Code |
| GitHub Actions workflow | — | ✅ (mirrors portfolio) | Claude Code |
| Ruff + Pyright config | — | ✅ | Claude Code |

### Stage 6: Deployment & Docs

| Task | Do yourself | Delegate to AI | Tool |
|------|-------------|----------------|------|
| Cloudflare DNS record | ✅ | — | Cloudflare dashboard |
| VPS setup | ✅ | — | SSH |
| Nginx config (prod) | — | ✅ (adapt from portfolio) | Claude Code |
| Origin certificate | ✅ | — | Cloudflare dashboard |
| README with architecture diagram | ✅ Write narrative | Polish + Mermaid diagrams | Claude Code |
| Portfolio project entry | ✅ | — | Django Admin |

---

## 5. Prompting Best Practices

### Do

- **Be specific about scope**: "Edit only `nodes.py`, do not touch `graph.py`"
- **Reference the SOT**: "Implement according to SOURCE_OF_TRUTH.md Section 5"
- **Provide constraints**: "Use async/await. No synchronous DB calls."
- **Ask for explanations**: "Implement X and explain why you chose this approach over Y"
- **Request incremental changes**: "Add the parse node first. I'll test it before adding chunk."

### Don't

- **Dump the whole project**: "Here's my codebase, make it better" — too vague
- **Skip understanding**: If AI writes code you can't explain, stop and learn
- **Trust blindly**: Always run tests after AI changes. Always read diffs.
- **Over-optimize prompts**: A clear, simple instruction beats a 500-word prompt

### Escape hatch

If an AI tool generates something that feels wrong or over-engineered:
1. Ask the web UI: "Is this the standard/idiomatic way to do X in [framework] as of 2026?"
2. Check the framework's official docs
3. Simplify. The best code is the simplest code that works correctly.

---

## 6. Cost Optimization for AI-Assisted Development

### Development phase (your subscriptions cover most usage)

- **Claude Code**: Unlimited within subscription. Use as primary tool.
- **ChatGPT / Claude Web UI**: Unlimited within subscription. Use for learning + planning.
- **GitHub Copilot**: Unlimited within subscription. Keep enabled for autocomplete.
- **OpenCode + OpenRouter**: Pay-per-token. Use strategically.

### OpenRouter budget management

For the ~10€ demo budget:

**During development** (use subscription tools instead):
- Avoid using OpenRouter for coding tasks — that's what Claude Code is for
- Only use OpenRouter to test DocForge's actual extraction functionality

**During demo availability**:
- Rate limit: 10 extractions/hour per IP (Redis-enforced)
- Model whitelist: only cheap models in demo mode (`gemini-2.0-flash-001`, `gpt-4o-mini`)
- Cache: Redis cache for identical document+schema combinations
- BYOK: encourage users to bring their own key for heavy usage

**Cost estimate for demo**:
- Average extraction: ~2K input tokens, ~1K output tokens
- Using `gemini-2.0-flash-001`: ~$0.0006 per extraction
- 10€ budget ≈ ~16,000 extractions with Gemini Flash
- Even with Claude Sonnet: ~$0.018 per extraction ≈ ~550 extractions
- Realistically, demo traffic will be 10–50 extractions/day → months of runway

---

## 7. Version Control Workflow

### Branch strategy

Simple and effective for a solo project:

```
main ← production (deployed via CI/CD)
  └── dev ← active development
        ├── feat/langgraph-workflow
        ├── feat/api-endpoints
        ├── feat/frontend
        └── fix/sse-disconnect
```

- Work on `dev` or feature branches
- Merge to `main` only when a stage is complete and tests pass
- CI/CD deploys on `main` push

### Commit messages

Follow Conventional Commits — it looks professional and AI tools parse it well:
```
feat(workflow): implement self-correcting extraction loop
fix(api): handle SSE disconnection on client timeout
docs(readme): add architecture diagram and quick start
chore(docker): optimize multi-stage backend build
test(workflow): add mock LLM tests for retry logic
```

### Git workflow with AI

When using Claude Code for multi-file changes:
1. Always review the diff before committing: `git diff --stat` then `git diff`
2. Stage files individually if the change touches multiple concerns
3. Write commit messages yourself (not AI-generated) — they should reflect YOUR understanding

---

## 8. Quality Checkpoints

Run these before completing each stage:

```bash
# Backend quality checks
cd backend
uv run ruff check .                    # Linting
uv run ruff format --check .           # Formatting
uv run pyright .                       # Type checking
uv run pytest -v                       # Tests

# Frontend quality checks
cd frontend
npm run lint                           # ESLint
npm run build                          # TypeScript compilation
npm run test                           # Vitest

# Integration check
docker compose up --build              # Everything starts
curl http://localhost:8000/api/health   # Backend responds
```

If any check fails, fix it before moving to the next stage. No exceptions.

---

## 9. Learning Resources (Prioritized)

Complete these in order of relevance to each stage:

### Before Stage 2 (LangGraph) — REQUIRED

1. [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview) — 30 min
2. [LangGraph Quickstart](https://docs.langchain.com/oss/python/langgraph/tutorials/get-started/quick-start) — 1 hour hands-on
3. [LangGraph State with Pydantic](https://docs.langchain.com/oss/python/langgraph/how-to/state-model) — 20 min
4. [Structured Output with LangGraph](https://docs.langchain.com/oss/python/langgraph/how-to/pass-graph-state) — 30 min

### Before Stage 3 (SSE Streaming) — RECOMMENDED

5. [FastAPI StreamingResponse docs](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse) — 15 min
6. [SSE explained (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) — 15 min

### Reference (consult as needed)

7. [Pydantic v2 docs](https://docs.pydantic.dev/latest/) — validators, model_config, JSON Schema
8. [FastAPI docs](https://fastapi.tiangolo.com/) — dependency injection, file uploads
9. [SQLAlchemy 2.0 async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — async session patterns
10. [uv docs](https://docs.astral.sh/uv/) — project management, lockfiles

---

*This document should be committed to the repo root. AI tools will read it automatically and adapt their behavior accordingly. Update it if your workflow changes.*
