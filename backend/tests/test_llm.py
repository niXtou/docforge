"""Tests for the LLM factory (app/core/llm.py)."""

from unittest.mock import MagicMock

from pytest import MonkeyPatch

from app.core import llm as llm_module
from app.core.config import settings


def _capture_kwargs(monkeypatch: MonkeyPatch) -> dict[str, object]:
    """Patch ChatOpenRouter so get_llm's constructor kwargs are captured."""
    captured: dict[str, object] = {}

    def fake_ctor(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(llm_module, "ChatOpenRouter", fake_ctor)
    return captured


def test_get_llm_passes_timeout_in_milliseconds(monkeypatch: MonkeyPatch) -> None:
    """ChatOpenRouter treats `timeout` as milliseconds, so get_llm must convert.

    Regression guard: passing the configured seconds directly made a "60s"
    timeout fire after 60ms, read-timing-out every real generation.
    """
    captured = _capture_kwargs(monkeypatch)
    monkeypatch.setattr(settings, "llm_request_timeout", 60)
    monkeypatch.setattr(settings, "llm_max_retries", 2)

    llm_module.get_llm(model="google/gemini-3.1-flash-lite", api_key="k")

    assert captured["timeout"] == 60_000  # 60 seconds expressed in milliseconds
    assert captured["max_retries"] == 2


def test_get_llm_prefers_byok_key(monkeypatch: MonkeyPatch) -> None:
    """A caller-supplied key (BYOK) is used in place of the server key."""
    captured = _capture_kwargs(monkeypatch)
    monkeypatch.setattr(settings, "openrouter_api_key", "server-key")

    llm_module.get_llm(model="m", api_key="byok-key")
    assert captured["api_key"] == "byok-key"

    captured.clear()
    llm_module.get_llm(model="m", api_key=None)
    assert captured["api_key"] == "server-key"
