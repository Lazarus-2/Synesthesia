"""Chain tests (Plan 3 D2).

Cover the chains that are pure-Python (similarity, llm_factory routing,
prompt formatting). LLM-invoking paths are mocked so tests stay hermetic.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# similarity_chain (no LLM)
# ---------------------------------------------------------------------------

class TestSimilarity:
    def test_embed_progression_is_normalized(self):
        from backend.chains.similarity_chain import embed_progression
        vec = embed_progression(["C", "G", "Am", "F"])
        norm = sum(v * v for v in vec) ** 0.5
        assert vec is not None and len(vec) == 12
        assert 0.99 <= norm <= 1.01, f"vector should be L2-normalized; got {norm}"

    def test_embed_empty_returns_zero_vector(self):
        from backend.chains.similarity_chain import embed_progression
        assert embed_progression([]) == [0.0] * 12

    def test_embed_v2_is_36_dim(self):
        from backend.chains.similarity_chain import embed_progression_v2
        vec = embed_progression_v2(["C", "G", "Am", "F"])
        assert len(vec) == 36, "v2 = 12 pitch + 12 transitions + 12 qualities"

    def test_embed_v2_key_invariance(self):
        """I-V-vi-IV in C and the same progression in G should embed nearly identically."""
        from backend.chains.similarity_chain import embed_progression_v2
        c_vec = embed_progression_v2(["C", "G", "Am", "F"], key="C major")
        g_vec = embed_progression_v2(["G", "D", "Em", "C"], key="G major")
        # Cosine similarity
        dot = sum(a * b for a, b in zip(c_vec, g_vec))
        n_c = sum(a * a for a in c_vec) ** 0.5
        n_g = sum(a * a for a in g_vec) ** 0.5
        sim = dot / (n_c * n_g)
        assert sim > 0.99, f"key-rotated progressions should match closely; got {sim}"

    def test_find_similar_returns_top_k(self):
        from backend.chains.similarity_chain import find_similar
        results = find_similar(["C", "G", "Am", "F"], k=2)
        assert len(results) == 2
        for r in results:
            assert {"title", "artist", "progression", "score"} <= r.keys()
        # Scores should be sorted descending
        assert results[0]["score"] >= results[1]["score"]

    def test_find_similar_handles_unknown_chord(self):
        from backend.chains.similarity_chain import find_similar
        # ``N.C.`` and empty strings shouldn't crash
        results = find_similar(["N.C.", "", "Cmaj7"], k=3)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# llm_factory (provider routing, no real API calls)
# ---------------------------------------------------------------------------

class TestLLMFactory:
    def test_unknown_provider_raises(self):
        from backend.chains.llm_factory import _build_provider_llm
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            _build_provider_llm("not-a-provider", model="x", temperature=0.0, api_key="x")

    def test_openai_requires_key(self):
        from backend.chains.llm_factory import _build_provider_llm
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            _build_provider_llm("openai", model="gpt-x", temperature=0.0, api_key="")

    def test_fallback_observer_wraps_runnable(self):
        from backend.chains.llm_factory import (
            _wrap_with_observable_fallback, get_fallback_stats, reset_fallback_stats,
        )
        from langchain_core.runnables import RunnableLambda
        # Primary always fails, fallback always succeeds.
        primary = RunnableLambda(lambda _x: (_ for _ in ()).throw(RuntimeError("boom")))
        fallback = RunnableLambda(lambda x: f"recovered:{x}")
        reset_fallback_stats()
        wrapped = _wrap_with_observable_fallback(
            primary, fallback, primary_name="alpha", fallback_name="beta",
        )
        assert wrapped.invoke("test") == "recovered:test"
        assert get_fallback_stats() == {"alpha->beta": 1}


# ---------------------------------------------------------------------------
# chat_chain context injection (no LLM)
# ---------------------------------------------------------------------------

class TestChatContext:
    def test_context_renders_with_key_tempo_progression(self):
        from backend.chains.chat_chain import _format_analysis_context
        analysis = {
            "title": "Synthetic", "key": "C major", "tempo": 120,
            "chords": [{"chord": "C"}, {"chord": "G"}, {"chord": "Am"}, {"chord": "F"}],
            "roman": {"progression": ["I", "V", "vi", "IV"]},
        }
        ctx = _format_analysis_context(analysis)
        assert ctx is not None
        assert "C major" in ctx
        assert "120" in ctx
        assert "I → V → vi → IV" in ctx
        assert "Synthetic" in ctx

    def test_context_none_when_analysis_missing(self):
        from backend.chains.chat_chain import _format_analysis_context
        # Empty dict is falsy and treated as "no analysis" — matches None case.
        assert _format_analysis_context(None) is None
        assert _format_analysis_context({}) is None

    def test_context_uses_unknown_key_when_only_partial_data(self):
        from backend.chains.chat_chain import _format_analysis_context
        # A populated dict missing ``key`` should still render with a fallback.
        ctx = _format_analysis_context({"tempo": 100})
        assert ctx is not None
        assert "Unknown" in ctx

    def test_build_history_prepends_system_when_analysis_given(self):
        from backend.chains.chat_chain import _build_history
        from langchain_core.messages import SystemMessage
        msgs = _build_history(
            [{"role": "user", "content": "hi"}],
            analysis={"key": "A minor", "tempo": 90, "chords": [{"chord": "Am"}]},
        )
        assert isinstance(msgs[0], SystemMessage)
        assert "A minor" in msgs[0].content

    def test_get_chat_response_falls_back_on_llm_error(self):
        from backend.chains import chat_chain
        # Force build_llm to raise so the chain hits its except branch.
        with patch.object(chat_chain, "build_llm", side_effect=RuntimeError("no api key")):
            reply = chat_chain.get_chat_response("test", [])
        assert "AURA Transmission Offline" in reply


# ---------------------------------------------------------------------------
# instrument_chain auto-capo helper
# ---------------------------------------------------------------------------

class TestAutoCapo:
    def test_open_chords_pick_no_capo_or_better(self):
        """C-G-Am-F: open shapes are fine but capo 5 turns F→C so might rank higher."""
        from backend.chains.instrument_chain import _auto_capo
        result = _auto_capo(["C", "G", "Am", "F"])
        # Either the function says no capo or a fret that yields easier shapes.
        assert result is None or 1 <= result <= 7

    def test_tricky_keys_picks_capo_2(self):
        from backend.chains.instrument_chain import _auto_capo
        # F#m-D-A-E with capo 2 -> Em-C-G-D (all open).
        assert _auto_capo(["F#m", "D", "A", "E"]) == 2

    def test_empty_list_returns_none(self):
        from backend.chains.instrument_chain import _auto_capo
        assert _auto_capo([]) is None


# ---------------------------------------------------------------------------
# theory_chain TheoryExplanation flattener
# ---------------------------------------------------------------------------

class TestTheoryFlattener:
    def test_required_only(self):
        from backend.chains.theory_chain import TheoryExplanation, _flatten
        te = TheoryExplanation(
            key_summary="The song is in C major.",
            function_explanation="C tonic, G dominant.",
        )
        out = _flatten(te)
        assert "C major" in out
        assert "G dominant" in out

    def test_full_render_includes_pattern_and_similar(self):
        from backend.chains.theory_chain import TheoryExplanation, _flatten
        te = TheoryExplanation(
            key_summary="Key: G.",
            function_explanation="Tonic, dominant, …",
            pattern_name="I-V-vi-IV",
            notable_techniques=["modal mixture"],
            similar_song="Let It Be — Beatles",
        )
        out = _flatten(te)
        assert "**Pattern:**" in out
        assert "modal mixture" in out
        assert "Let It Be" in out
