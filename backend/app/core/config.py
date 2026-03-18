"""Application configuration via Pydantic Settings.

HOW CONFIGURATION WORKS
────────────────────────
Pydantic Settings reads values in this priority order (highest wins):
  1. Real environment variables (e.g. set in docker-compose.yml or the shell)
  2. Variables in the .env file (copy .env.example → .env to get started)
  3. The `default=` values defined in each Field() below

Field names are case-insensitive by design (case_sensitive=False), so
DATABASE_URL and database_url in .env both map to `settings.database_url`.

Usage anywhere in the app:
  from app.core.config import settings
  settings.database_url  # resolved value
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All environment-based configuration for DocForge."""

    model_config = SettingsConfigDict(
        env_file=".env",  # load from .env file if present
        env_file_encoding="utf-8",
        case_sensitive=False,  # DATABASE_URL == database_url == DataBase_Url
    )

    # ── App ───────────────────────────────────────────────────────────────────
    secret_key: str = Field(default="change-me-in-production")  # used to sign auth tokens
    debug: bool = Field(default=False)  # enables verbose SQL + tracebacks
    allowed_origins: list[str] = Field(default=["http://localhost:5173"])  # frontend dev server

    # ── Database ──────────────────────────────────────────────────────────────
    # asyncpg is an async Postgres driver required by SQLAlchemy's async mode.
    # In Docker the host is the service name "db"; outside Docker use "localhost".
    database_url: str = Field(
        default="postgresql+asyncpg://docforge_user:password@localhost:5432/docforge_db"
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")  # used for job queuing (Stage 4+)

    # ── LLM Providers ─────────────────────────────────────────────────────────
    # All LLM calls go through OpenRouter, which is a unified gateway for models
    # from Anthropic, OpenAI, Google, and others. One API key gives access to all
    # of them using an OpenAI-compatible request format.
    #
    # BYOK (Bring Your Own Key): users may supply their own key per request.
    # If they do, their key is used; otherwise the server key below is used.
    openrouter_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")  # reserved for future direct routing
    openai_api_key: str = Field(default="")
    google_api_key: str = Field(default="")

    # ── Rate Limiting (demo mode) ─────────────────────────────────────────────
    # In demo mode (no auth), users are limited to N requests/hour and
    # restricted to a curated list of cost-effective models.
    demo_rate_limit_per_hour: int = Field(default=10)
    demo_allowed_models: list[str] = Field(
        default=[
            "google/gemini-2.0-flash",  # fast, very cost-effective
            "openai/gpt-4o-mini",  # good reasoning at low cost
            "openai/gpt-5.4-nano",  # latest nano model
            "meta-llama/llama-3.3-70b-instruct",  # open-weight, cheap via OpenRouter
        ]
    )


# Singleton — import this instance everywhere instead of re-instantiating Settings().
settings = Settings()
