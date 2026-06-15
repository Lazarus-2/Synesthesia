"""FT-01 + degradation-status: AnalysisState reducer semantics.

These tests pin the *shape* of AnalysisState — that ``errors`` is an
append-only (operator.add) channel, that ``feature_error`` is a plain
last-write-wins channel, and that ``status`` is a typed literal. They run
without ML/LLM/Mongo by inspecting the TypedDict annotations and by driving
a tiny StateGraph that exercises the reducer at fan-in.
"""

from __future__ import annotations

import operator
import typing

from langgraph.graph import END, START, StateGraph

from backend.graph.state import AnalysisState


def _reducer_of(field: str):
    """Return the reducer callable bound to an Annotated AnalysisState field.

    LangGraph stores the reducer as the second arg of ``Annotated[...]``;
    ``typing.get_type_hints(include_extras=True)`` surfaces it.
    """
    hints = typing.get_type_hints(AnalysisState, include_extras=True)
    meta = getattr(hints[field], "__metadata__", ())
    return meta[0] if meta else None


class TestErrorsReducer:
    def test_errors_uses_operator_add_reducer(self):
        assert _reducer_of("errors") is operator.add

    def test_feature_error_has_no_reducer(self):
        # Plain last-write-wins: no Annotated metadata.
        assert _reducer_of("feature_error") is None

    def test_status_field_is_declared(self):
        hints = typing.get_type_hints(AnalysisState, include_extras=True)
        assert "status" in hints

    def test_errors_concurrent_appends_merge(self):
        """Two parallel nodes each appending one error must NOT raise
        InvalidUpdateError; the operator.add reducer concatenates them."""
        g = StateGraph(AnalysisState)

        def fan_a(_state):
            return {"errors": ["a-down"]}

        def fan_b(_state):
            return {"errors": ["b-down"]}

        g.add_node("a", fan_a)
        g.add_node("b", fan_b)
        g.add_edge(START, "a")
        g.add_edge(START, "b")
        g.add_edge("a", END)
        g.add_edge("b", END)
        graph = g.compile()

        result = graph.invoke({"errors": [], "retries": 0})
        assert sorted(result["errors"]) == ["a-down", "b-down"]


from backend.graph.nodes import should_retry


class TestShouldRetryReadsFeatureError:
    def test_clean_state_is_ok(self):
        assert should_retry({}) == "ok"
        assert should_retry({"feature_error": None}) == "ok"

    def test_latest_attempt_failed_under_cap_retries(self):
        assert should_retry({"feature_error": "boom", "retries": 0}) == "retry"
        assert should_retry({"feature_error": "boom", "retries": 1}) == "retry"

    def test_latest_attempt_failed_at_cap_fails(self):
        assert should_retry({"feature_error": "boom", "retries": 2}) == "fail"

    def test_stale_errors_log_does_not_force_retry(self):
        """FT-01 heart: a successful retry clears feature_error even though the
        append-only ``errors`` log still holds the prior failure string."""
        state = {
            "errors": ["Feature extraction failed: transient decode error"],
            "feature_error": None,
            "retries": 1,
        }
        assert should_retry(state) == "ok"


class TestFeaturesNodeFailThenSucceed:
    def test_fail_then_succeed_yields_usable_analysis(self, monkeypatch):
        """A first attempt that throws, then a second that succeeds, must end
        with populated features and feature_error cleared to None."""
        import backend.graph.nodes as nodes_mod

        calls = {"n": 0}

        def flaky_key_tempo(_path):
            from backend.ml.key_estimation import KeyTempoResult

            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient decode error")
            return KeyTempoResult("C major", 0.8, 120.0, 0.4)

        monkeypatch.setattr(
            "backend.ml.key_estimation.estimate_key_and_tempo", flaky_key_tempo
        )
        from backend.ml.beat_tracking import BeatTrackingResult
        monkeypatch.setattr(
            "backend.ml.beat_tracking.track_beats", lambda _p: BeatTrackingResult()
        )
        monkeypatch.setattr(
            "backend.ml.chord_detection.detect_chords", lambda _p, beats=None: []
        )
        monkeypatch.setattr(
            "backend.ml.structure_detection.detect_sections", lambda _p: []
        )

        # Attempt 1 — fails.
        out1 = nodes_mod.features_node({"audio_path": "/tmp/x.wav", "retries": 0})
        assert out1["feature_error"] is not None
        assert out1["errors"]  # appended to the degradation log
        assert should_retry({**out1}) == "retry"

        # Attempt 2 — succeeds; feature_error cleared, features present.
        out2 = nodes_mod.features_node(
            {"audio_path": "/tmp/x.wav", "retries": out1["retries"]}
        )
        assert out2["feature_error"] is None
        assert out2["key"] == "C major"
        assert should_retry({**out2}) == "ok"
