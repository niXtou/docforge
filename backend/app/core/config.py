"""Application configuration via Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All environment-based configuration for DocForge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    secret_key: str = Field(default="change-me-in-production")
    debug: bool = Field(default=False)
    allowed_origins: list[str] = Field(default=["http://localhost:5173"])

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://docforge_user:password@localhost:5432/docforge_db"
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # LLM Providers
    openrouter_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    google_api_key: str = Field(default="")

    # Rate Limiting (demo mode)
    demo_rate_limit_per_hour: int = Field(default=10)
    demo_allowed_models: list[str] = Field(
        default=[
            "anthropic/claude-sonnet-4-20250514",
            "google/gemini-2.0-flash",
            "openai/gpt-4o-mini",
        ]
    )


settings = Settings()
