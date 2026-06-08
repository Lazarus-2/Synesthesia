"""CHAT_* settings (Group D.3, spec §9).

CHAT_PROVIDER/CHAT_MODEL default to LLM_PROVIDER/MODEL_NAME so chat is
provider-agnostic with no separate default; the rest are plain tunables.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def fresh_settings(monkeypatch):
    # A complete, valid env so the model-validator (api-key gate) passes.
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MODEL_NAME", "gpt-4o-mini")
    from backend.config import Settings

    return Settings


def test_chat_defaults(fresh_settings):
    s = fresh_settings()
    assert s.chat_tools_enabled is True
    assert s.chat_max_tool_iters == 4
    assert s.chat_history_turns == 10
    assert s.chat_tutor_default is False
    assert s.chat_user_daily_token_budget == 200000


def test_chat_provider_model_default_to_llm(fresh_settings):
    s = fresh_settings()
    # Empty CHAT_PROVIDER/CHAT_MODEL resolve to the base LLM provider/model.
    assert s.effective_chat_provider == "openai"
    assert s.effective_chat_model == "gpt-4o-mini"


def test_chat_provider_override(monkeypatch, fresh_settings):
    monkeypatch.setenv("CHAT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("CHAT_MODEL", "claude-3-5-haiku-latest")
    s = fresh_settings()
    assert s.effective_chat_provider == "anthropic"
    assert s.effective_chat_model == "claude-3-5-haiku-latest"


def test_chat_budget_override(monkeypatch, fresh_settings):
    monkeypatch.setenv("CHAT_USER_DAILY_TOKEN_BUDGET", "50000")
    assert fresh_settings().chat_user_daily_token_budget == 50000
