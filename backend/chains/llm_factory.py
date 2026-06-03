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

Fallback observability (Plan 2 B5)
----------------------------------
``.with_fallbacks()`` silently swallows the primary's exception. We wrap the
returned Runnable so a fallback activation logs (and increments a metric
counter when one is available) instead of being invisible. Operators
currently can't tell the difference between a "primary worked" and
"fallback rescued us" path.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableLambda

from backend.config import get_settings

logger = logging.getLogger(__name__)

# In-process counter for fallback activations, keyed by ``primary->fallback``.
# Exposed via :func:`get_fallback_stats` for admin endpoints and tests; no
# metrics dependency yet — we'll wire Prometheus / OTel in Plan 2 H1.
_fallback_activation_count: dict[str, int] = {}


def get_fallback_stats() -> dict[str, int]:
    """Return a snapshot of fallback activation counts keyed by ``primary->fallback``."""
    return dict(_fallback_activation_count)


def reset_fallback_stats() -> None:
    """Reset the in-process counter. For tests."""
    _fallback_activation_count.clear()


def _wrap_with_observable_fallback(
    primary: BaseChatModel, fallback: BaseChatModel,
    primary_name: str, fallback_name: str,
) -> Any:
    """Compose primary + fallback so each fallback activation is logged.

    ``RunnableWithFallbacks`` silently catches the primary's exception and
    routes to the fallback. We need a side-effect on that error path. The
    portable way (across LangChain versions) is to wrap ``primary`` in a
    :class:`RunnableLambda` that catches, logs, and re-raises — then chain
    that wrapped primary into ``.with_fallbacks([fallback])`` so the normal
    routing kicks in.
    """
    def _on_primary_error(exc: BaseException) -> None:
        key = f"{primary_name}->{fallback_name}"
        _fallback_activation_count[key] = _fallback_activation_count.get(key, 0) + 1
        logger.warning(
            "LLM fallback activated: primary=%s fallback=%s reason=%s message=%r",
            primary_name, fallback_name, type(exc).__name__, str(exc)[:200],
        )

    async def _ainvoke_with_logging(inp, *, _primary=primary):
        try:
            return await _primary.ainvoke(inp)
        except Exception as e:
            _on_primary_error(e)
            raise

    def _invoke_with_logging(inp, *, _primary=primary):
        try:
            return _primary.invoke(inp)
        except Exception as e:
            _on_primary_error(e)
            raise

    logged_primary = RunnableLambda(_invoke_with_logging, afunc=_ainvoke_with_logging)
    return logged_primary.with_fallbacks([fallback])

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

    elif provider == "ollama":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=resolved_model,
            temperature=temperature,
            api_key="not-needed",  # placeholder; Ollama doesn't auth
            base_url="http://localhost:11434/v1",
        )

    else:
        raise ValueError(
            f"Unknown LLM provider {provider!r}. "
            f"Supported: openai, anthropic, gemini, groq, openrouter, ollama."
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
        "ollama": "",  # Ollama runs locally and doesn't auth
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

    # Optional fallback — auto-tries second provider on any exception.
    # The wrapper logs every fallback activation (Plan 2 B5).
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
        return _wrap_with_observable_fallback(
            primary, fallback,
            primary_name=provider,
            fallback_name=fallback_provider,
        )

    return primary
