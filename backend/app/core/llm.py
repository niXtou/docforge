"""LLM provider factory — OpenRouter-first with BYOK support.

WHAT IS OPENROUTER?
────────────────────
OpenRouter (openrouter.ai) is a unified API gateway that lets you access models
from Anthropic, OpenAI, Google, and others through a single endpoint and API key.

Model strings follow the format "provider/model-name", e.g.:
  "google/gemini-2.0-flash-001"
  "openai/gpt-4o-mini"
  "anthropic/claude-sonnet-4.5"

We use the official `langchain-openrouter` package (first-party LangChain
integration released March 2026) which natively supports OpenRouter's features
like provider routing, app attribution, and structured output.

BYOK (BRING YOUR OWN KEY)
──────────────────────────
Users can optionally pass their own OpenRouter API key in the extraction
request. If they do, we use it; otherwise we fall back to the server's key.
This lets power users pay for their own usage and bypass demo rate limits.
"""

from langchain_openrouter import ChatOpenRouter

from app.core.config import settings


def get_llm(
    model: str = "google/gemini-2.0-flash-001",
    api_key: str | None = None,
    temperature: float = 0.0,
) -> ChatOpenRouter:
    """Return a ChatOpenRouter instance for the given model.

    Args:
        model: OpenRouter model string (e.g. "google/gemini-2.0-flash-001").
        api_key: BYOK API key; falls back to the server's key if None.
        temperature: Sampling temperature. 0.0 means deterministic output,
            which is what we want for structured data extraction.
    """
    # Use the caller's key if provided (BYOK), otherwise use the server key.
    effective_key = api_key or settings.openrouter_api_key

    return ChatOpenRouter(
        model=model,
        api_key=effective_key,  # type: ignore[arg-type]
        temperature=temperature,
        # Attribution headers — OpenRouter uses these to identify the calling app.
        # They appear in your OpenRouter dashboard and help with rate limit attribution.
        app_url="https://docforge.nstoug.com",
        app_title="DocForge",
    )
