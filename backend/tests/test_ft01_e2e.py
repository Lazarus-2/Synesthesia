"""FT-01 end-to-end against the real production graph.

Proves three properties through ``build_graph`` (the worker's graph):

  1. A feature-extraction attempt that FAILS then SUCCEEDS on retry yields a
     usable analysis whose derived status != "failed".
  2. A degraded fan-out (LLM down) persists status="degraded" with the
     error recorded in the append-only ``errors`` log.
  3. Concurrent fan-out appends merge via operator.add — no InvalidUpdateError.
"""

from __future__ import annotations

import asyncio

import pytest
from langgraph.checkpoint.memory import MemorySaver

from backend.graph.graph import build_graph
from backend.graph.status import derive_status
from backend.schemas import ChordEvent


def _run(graph, state, thread_id):
    async def go():
        return await graph.ainvoke(
            state,
            config={
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 50,
            },
        )

    return asyncio.run(go())


@pytest.fixture
def patched_pipeline(monkeypatch):
    """Stub ingest/validate/ML/LLM so the graph runs hermetically. Feature
    extraction is flaky: it raises on its first call, succeeds after.

    ``build_graph`` binds functions from ``backend.graph.graph``'s local
    namespace (imported at module level). Patching must target that namespace,
    not ``backend.graph.nodes``, or the already-bound references are unchanged.
    """
    import backend.graph.graph as graph_mod

    monkeypatch.setattr(
        graph_mod, "ingest_node", lambda s: {"audio_path": "/tmp/job_e2e.wav"}
    )
    monkeypatch.setattr(graph_mod, "validate_audio_node", lambda s: {})

    calls = {"features": 0}
    real_chords = [ChordEvent(chord="C", start=0.0, end=1.0)]

    def flaky_features(state):
        calls["features"] += 1
        next_retries = state.get("retries", 0) + 1
        if calls["features"] == 1:
            msg = "Feature extraction failed: transient decode error"
            return {"errors": [msg], "feature_error": msg, "retries": next_retries}
        return {
            "key": "C major",
            "tempo": 120.0,
            "beats": [],
            "chords": real_chords,
            "sections": [],
            "retries": next_retries,
            "feature_error": None,
        }

    monkeypatch.setattr(graph_mod, "features_node", flaky_features)
    monkeypatch.setattr(graph_mod, "roman_analysis_node", lambda s: {"roman": None})
    # Stub the heavy/IO fan-out so the graph stays hermetic.
    monkeypatch.setattr(
        graph_mod, "theory_node", lambda s: {"theory_explanation": "ok"}
    )
    monkeypatch.setattr(
        graph_mod, "instrument_node", lambda s: {"instrument_guide": None}
    )
    monkeypatch.setattr(graph_mod, "similarity_node", lambda s: {"similar_songs": []})
    monkeypatch.setattr(graph_mod, "stems_node", lambda s: {})
    return calls


def test_fail_then_succeed_yields_usable_non_failed_run(patched_pipeline):
    graph = build_graph(MemorySaver())
    result = _run(
        graph,
        {"audio_path": "/tmp/job_e2e.wav", "errors": [], "retries": 0},
        "ft01-recover",
    )
    assert patched_pipeline["features"] == 2  # failed once, retried, succeeded
    assert result.get("chords"), "recovered run must carry usable chords"
    assert result.get("feature_error") is None
    assert derive_status(result) != "failed"


def test_degraded_fanout_records_error_and_marks_degraded(monkeypatch):
    import backend.graph.graph as graph_mod

    monkeypatch.setattr(
        graph_mod, "ingest_node", lambda s: {"audio_path": "/tmp/job_deg.wav"}
    )
    monkeypatch.setattr(graph_mod, "validate_audio_node", lambda s: {})
    monkeypatch.setattr(
        graph_mod,
        "features_node",
        lambda s: {
            "key": "C major",
            "tempo": 120.0,
            "beats": [],
            "chords": [ChordEvent(chord="C", start=0.0, end=1.0)],
            "sections": [],
            "retries": 1,
            "feature_error": None,
        },
    )
    monkeypatch.setattr(graph_mod, "roman_analysis_node", lambda s: {"roman": None})
    # theory_node degrades: appends an error AND returns fallback text.
    monkeypatch.setattr(
        graph_mod,
        "theory_node",
        lambda s: {
            "errors": ["theory: LLM commentary engine offline"],
            "theory_explanation": "deterministic fallback",
        },
    )
    monkeypatch.setattr(
        graph_mod, "instrument_node", lambda s: {"instrument_guide": None}
    )
    monkeypatch.setattr(graph_mod, "similarity_node", lambda s: {"similar_songs": []})
    monkeypatch.setattr(graph_mod, "stems_node", lambda s: {})

    graph = build_graph(MemorySaver())
    result = _run(
        graph,
        {"audio_path": "/tmp/job_deg.wav", "errors": [], "retries": 0},
        "ft01-degraded",
    )
    assert any("theory" in e.lower() for e in result["errors"])
    assert derive_status(result) == "degraded"


def test_concurrent_fanout_appends_do_not_raise(monkeypatch):
    """Two fan-out nodes both append on the SAME super-step. With the
    operator.add reducer this merges; without it LangGraph raises
    InvalidUpdateError."""
    import backend.graph.graph as graph_mod

    monkeypatch.setattr(
        graph_mod, "ingest_node", lambda s: {"audio_path": "/tmp/job_cc.wav"}
    )
    monkeypatch.setattr(graph_mod, "validate_audio_node", lambda s: {})
    monkeypatch.setattr(
        graph_mod,
        "features_node",
        lambda s: {
            "key": "C major",
            "tempo": 120.0,
            "beats": [],
            "chords": [ChordEvent(chord="C", start=0.0, end=1.0)],
            "sections": [],
            "retries": 1,
            "feature_error": None,
        },
    )
    monkeypatch.setattr(graph_mod, "roman_analysis_node", lambda s: {"roman": None})
    monkeypatch.setattr(
        graph_mod,
        "theory_node",
        lambda s: {"errors": ["theory down"], "theory_explanation": "x"},
    )
    monkeypatch.setattr(
        graph_mod,
        "instrument_node",
        lambda s: {"errors": ["instrument down"], "instrument_guide": None},
    )
    monkeypatch.setattr(
        graph_mod,
        "similarity_node",
        lambda s: {"errors": ["similarity down"], "similar_songs": []},
    )
    monkeypatch.setattr(
        graph_mod, "stems_node", lambda s: {"errors": ["stems down"]}
    )

    graph = build_graph(MemorySaver())
    result = _run(
        graph,
        {"audio_path": "/tmp/job_cc.wav", "errors": [], "retries": 0},
        "ft01-concurrent",
    )
    # All four degradation strings present; no exception was raised.
    assert sorted(result["errors"]) == [
        "instrument down",
        "similarity down",
        "stems down",
        "theory down",
    ]
    assert derive_status(result) == "degraded"
