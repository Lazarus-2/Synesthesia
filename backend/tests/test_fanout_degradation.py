"""Fan-out nodes must record a degradation error string (not swallow it).

When an LLM is unreachable or a fan-out helper throws, the node should still
return its graceful fallback AND append a human-readable string to ``errors``
so the worker can derive status="degraded".
"""

from __future__ import annotations

import backend.graph.nodes as nodes_mod
from backend.schemas import ChordEvent


def _base_state():
    return {
        "key": "C major",
        "tempo": 120.0,
        "chords": [ChordEvent(chord="C", start=0.0, end=1.0)],
        "instrument": "guitar",
        "difficulty": "beginner",
        "roman": None,
    }


class TestTheoryDegradation:
    def test_llm_down_records_error_and_still_returns_text(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("ollama refused connection")

        monkeypatch.setattr("backend.chains.theory_chain.build_theory_chain", boom)
        out = nodes_mod.theory_node(_base_state())
        assert out["theory_explanation"]  # fallback prose present
        assert out.get("errors"), "theory_node must append a degradation error"
        assert any("theory" in e.lower() for e in out["errors"])


class TestInstrumentDegradation:
    def test_llm_down_records_error_and_still_returns_guide(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("ollama refused connection")

        monkeypatch.setattr(
            "backend.chains.instrument_chain.build_instrument_chain", boom
        )
        out = nodes_mod.instrument_node(_base_state())
        assert out["instrument_guide"] is not None  # fallback guide present
        assert out.get("errors")
        assert any("instrument" in e.lower() for e in out["errors"])


class TestSimilarityDegradation:
    def test_similarity_failure_records_error(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("golden_songs.json missing")

        monkeypatch.setattr("backend.chains.similarity_chain.find_similar", boom)
        out = nodes_mod.similarity_node(_base_state())
        assert out["similar_songs"] == []  # graceful empty list
        assert out.get("errors")
        assert any("similar" in e.lower() for e in out["errors"])


class TestStemsDegradation:
    def test_stems_failure_records_error(self, monkeypatch):
        from backend.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "enable_stems", True, raising=False)

        def boom(*_a, **_k):
            raise RuntimeError("demucs CUDA OOM")

        monkeypatch.setattr("backend.ml.stem_separation.separate_stems", boom)
        out = nodes_mod.stems_node({"audio_path": "/tmp/job123_x.wav"})
        assert out.get("stems", {}) == {}
        assert out.get("errors")
        assert any("stem" in e.lower() for e in out["errors"])
