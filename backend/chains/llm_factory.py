"""
Multi-provider LLM factory with native provider support and fallback chains.
Vault ref: 05-Production-Systems/02-Latency-Cost-Quality.md

Supports 6 providers:
  - 'openai':     Native ChatOpenAI (GPT-5.x family)
  - 'anthropic':  Native ChatAnthropic (Claude Sonnet 4 / Opus 4)
  - 'gemini':     Native ChatGoogleGenerativeAI (Gemini 3.x)
  - 'groq':       OpenAI-compat (Llama 3.3 on Groq LPU)
  - 'openrouter': OpenAI-compat (multi-model aggregator)
  - 'ollama':     OpenAI-compat (local Qwen3, Gemma4, etc.)
"""
from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Provider → default model mapping (May 2026)
_PROVIDER_DEFAULTS: dict[str, str] = {
    "openai":     "gpt-5.3-instant",
    "anthropic":  "claude-sonnet-4-20250514",
    "gemini":     "gemini-3.1-flash",
    "groq":       "llama-3.3-70b-versatile",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "ollama":     "qwen3:8b",
}


def _build_provider_llm(
    provider: str,
    model: str,
    temperature: float,
    api_key: str = "",
) -> BaseChatModel:
    """Build a single LLM instance for the given provider.

    Uses native LangChain packages for OpenAI, Anthropic, and Gemini
    to get full feature support (native structured output, prompt caching,
    streaming tool use). Uses ChatOpenAI OpenAI-compat shim for Groq,
    OpenRouter, and Ollama.
    """
    resolved_model = model or _PROVIDER_DEFAULTS.get(provider, "qwen3:8b")

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when LLM_PROVIDER=openai. "
                "Set it in your .env file."
            )
        return ChatOpenAI(
            model=resolved_model,
            temperature=temperature,
            api_key=api_key,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic. "
                "Set it in your .env file."
            )
        return ChatAnthropic(
            model=resolved_model,
            temperature=temperature,
            api_key=api_key,
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when LLM_PROVIDER=gemini. "
                "Set it in your .env file."
            )
        return ChatGoogleGenerativeAI(
            model=resolved_model,
            temperature=temperature,
            google_api_key=api_key,
        )

    elif provider == "groq":
        from langchain_openai import ChatOpenAI
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is required when LLM_PROVIDER=groq. "
                "Set it in your .env file."
            )
        return ChatOpenAI(
            model=resolved_model,
            temperature=temperature,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    elif provider == "openrouter":
        from langchain_openai import ChatOpenAI
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter. "
                "Set it in your .env file."
            )
        return ChatOpenAI(
            model=resolved_model,
            temperature=temperature,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    else:  # ollama (default)
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=resolved_model,
            temperature=temperature,
            api_key="ollama",  # dummy key required by client validation
            base_url="http://localhost:11434/v1",
        )


def _get_api_key(provider: str) -> str:
    """Resolve the correct API key for a provider from settings."""
    s = get_settings()
    key_map: dict[str, str] = {
        "openai": s.openai_api_key,
        "anthropic": s.anthropic_api_key,
        "gemini": s.gemini_api_key,
        "groq": s.groq_api_key,
        "openrouter": s.openrouter_api_key,
        "ollama": "ollama",
    }
    return key_map.get(provider, "")


def build_llm(temperature: float = 0.2) -> BaseChatModel:
    """Build LLM with optional fallback chain.

    Returns a Runnable that:
    1. Tries the primary provider (LLM_PROVIDER)
    2. Falls back to LLM_FALLBACK_PROVIDER on any exception

    Usage:
        llm = build_llm(temperature=0.3)
        result = llm.invoke("Hello")
        # or with structured output:
        structured = llm.with_structured_output(MySchema)
        result = structured.invoke("Extract data from ...")
    """
    s = get_settings()
    provider = (s.llm_provider or "ollama").lower()

    logger.info("Building LLM: provider=%s, model=%s", provider, s.model_name or "(default)")

    primary = _build_provider_llm(
        provider=provider,
        model=s.model_name,
        temperature=temperature,
        api_key=_get_api_key(provider),
    )

    # Optional fallback — auto-tries second provider on any exception
    fallback_provider = (s.llm_fallback_provider or "").lower()
    if fallback_provider and fallback_provider != provider:
        logger.info("Fallback configured: provider=%s, model=%s",
                     fallback_provider, s.llm_fallback_model or "(default)")
        fallback = _build_provider_llm(
            provider=fallback_provider,
            model=s.llm_fallback_model,
            temperature=temperature,
            api_key=_get_api_key(fallback_provider),
        )
        return primary.with_fallbacks([fallback])

    return primary
