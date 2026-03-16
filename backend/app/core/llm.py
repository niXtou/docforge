"""LLM provider factory — OpenRouter-first with BYOK support."""

from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_llm(
    model: str = "anthropic/claude-sonnet-4-20250514",
    api_key: str | None = None,
    temperature: float = 0.0,
) -> ChatOpenAI:
    """Return a ChatOpenAI instance pointed at OpenRouter.

    Args:
        model: OpenRouter model string.
        api_key: BYOK API key; falls back to server key if None.
        temperature: Sampling temperature.
    """
    effective_key = api_key or settings.openrouter_api_key
    return ChatOpenAI(
        model=model,
        api_key=effective_key,  # type: ignore[arg-type]
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
        default_headers={
            "HTTP-Referer": "https://docforge.nstoug.com",
            "X-Title": "DocForge",
        },
    )
