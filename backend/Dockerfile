# Multi-stage Dockerfile for DocForge backend
#
# Why multi-stage?
#   Stage 1 (builder) installs all dependencies using uv — this stage is large
#   because it contains build tools. Stage 2 (runtime) copies only the compiled
#   virtualenv and app code, producing a lean final image with no build tooling.
#
# Result: a small, production-safe image without dev tools or build artifacts.

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
# Use the official Python slim image as the base for installing dependencies.
FROM python:3.12-slim AS builder

# Copy the uv binary from its official image — uv is a fast Python package
# manager (written in Rust) that replaces pip + venv in this project.
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first (before app code) so Docker can cache this
# layer. If only app code changes, Docker reuses the cached dependency install.
COPY pyproject.toml uv.lock* ./

# --frozen:      fail if uv.lock is out of sync with pyproject.toml (reproducible builds)
# --no-dev:      skip dev-only packages (pytest, ruff, etc.) — not needed at runtime
# --no-editable: install the project as a regular package, not a symlink
RUN uv sync --frozen --no-dev --no-editable

# Copy application source and database migration files
COPY app/ app/
COPY alembic.ini .
COPY alembic/ alembic/

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
# Start fresh from a slim base — no uv, no build tools, no package cache.
FROM python:3.12-slim AS runtime

# Run as a non-root user for security. If the app is compromised, the attacker
# gets a limited user account rather than full root access inside the container.
RUN groupadd -r appuser && useradd -r -g appuser appuser
WORKDIR /app

# Copy only what the app needs to run from the builder stage.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/alembic /app/alembic

# Add the virtualenv's bin/ to PATH so Python uses the installed packages
ENV PATH="/app/.venv/bin:$PATH"

# PYTHONUNBUFFERED=1 forces stdout/stderr to flush immediately.
# Without this, log lines may not appear in `docker logs` until the buffer fills.
ENV PYTHONUNBUFFERED=1

# Switch to non-root before starting the server
USER appuser
EXPOSE 8000

# Production server: 2 worker processes, no --reload (use the compose file for dev)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
