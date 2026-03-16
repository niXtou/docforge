"""LLM provider factory — OpenRouter-first with BYOK support."""

# TODO (Stage 2): Implement get_llm() factory returning ChatOpenAI pointed at OpenRouter.
#
# from langchain_openai import ChatOpenAI
# from app.core.config import settings
#
# def get_llm(
#     model: str = "anthropic/claude-sonnet-4-20250514",
#     api_key: str | None = None,
#     temperature: float = 0.0,
# ) -> ChatOpenAI:
#     effective_key = api_key or settings.OPENROUTER_API_KEY
#     return ChatOpenAI(
#         model=model,
#         api_key=effective_key,
#         base_url="https://openrouter.ai/api/v1",
#         temperature=temperature,
#         default_headers={
#             "HTTP-Referer": "https://docforge.nstoug.com",
#             "X-Title": "DocForge",
#         },
#     )
