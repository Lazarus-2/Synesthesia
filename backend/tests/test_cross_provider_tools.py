"""Cross-provider tool-schema smoke test (spec §5 / §11).

Binding TOOLS to each provider class must not raise during schema conversion.
This is the matrix guard for "a single bound agent runs on all six providers".
No network: bind_tools only serialises the pydantic args_schema; fake keys are
fine because nothing is invoked.
"""

from __future__ import annotations

import pytest

from backend.chains.llm_factory import _build_provider_llm

pytest.importorskip(
    "backend.chains.aura_tools",
    reason="Group B aura_tools.TOOLS lands separately; smoke test activates then.",
)

# (provider, fake api key) — Ollama needs no key (local shim).
_PROVIDER_MATRIX = [
    ("openai", "sk-fake-openai"),
    ("anthropic", "sk-ant-fake"),
    ("gemini", "fake-gemini-key"),
    ("groq", "gsk-fake"),
    ("openrouter", "sk-or-fake"),
    ("ollama", ""),
]


@pytest.mark.parametrize("provider,api_key", _PROVIDER_MATRIX)
def test_tools_bind_to_every_provider_without_schema_error(provider, api_key):
    from backend.chains.aura_tools import TOOLS

    model = _build_provider_llm(
        provider=provider,
        model="",  # provider default
        temperature=0.7,
        api_key=api_key,
    )
    # Schema conversion happens eagerly inside bind_tools; if a tool's
    # args_schema is malformed for this provider it raises here.
    bound = model.bind_tools(TOOLS)
    assert bound is not None


def test_tools_list_is_the_canonical_seven():
    from backend.chains.aura_tools import TOOLS

    names = {getattr(t, "name", getattr(t, "__name__", "")) for t in TOOLS}
    assert names == {
        "transpose_progression",
        "suggest_capo",
        "get_chord_voicing",
        "get_chord_color",
        "find_similar_songs",
        "get_song_analysis",
        "lookup_theory",
    }
