"""Regression tests for the LangGraph routing (Plan 3 live-test fix).

The crashing scenario was:

  1. ``ingest_node`` rejects a malformed URL and sets ``state["errors"]``.
  2. ``validate_audio_node`` and ``features_node`` both short-circuit on
     pre-existing errors without touching ``retries``.
  3. ``should_retry`` saw ``errors`` + ``retries < 2`` and looped back to
     features forever, blowing past LangGraph's 10007 recursion ceiling.

These tests exercise the routing predicates and a minimal compiled graph
(without LLM / Mongo / librosa) to prove that:

  - An ingest-stage error terminates the pipeline at END immediately.
  - A validate-stage error terminates the pipeline at END immediately.
  - A genuine features error retries at most twice.
  - A clean run completes without entering retry logic.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.graph.nodes import has_errors_route, should_retry
from backend.graph.state import AnalysisState


class TestRouteHelpers:
    def test_has_errors_route_returns_ok_for_clean_state(self):
        assert has_errors_route({}) == "ok"
        assert has_errors_route({"errors": []}) == "ok"

    def test_has_errors_route_returns_fail_when_errors_present(self):
        assert has_errors_route({"errors": ["nope"]}) == "fail"

    def test_should_retry_returns_ok_for_clean_state(self):
        assert should_retry({}) == "ok"
        assert should_retry({"errors": []}) == "ok"

    def test_should_retry_returns_retry_once(self):
        # First failure: retries=0 (before features bumps it) → retry.
        assert should_retry({"errors": ["x"], "retries": 0}) == "retry"
        # Second failure: retries=1 → still retry (max_retries=2).
        assert should_retry({"errors": ["x"], "retries": 1}) == "retry"

    def test_should_retry_returns_fail_after_max(self):
        assert should_retry({"errors": ["x"], "retries": 2}) == "fail"


class TestIngestErrorRouting:
    def _build_mini_graph(self):
        """Build the routing skeleton with stub nodes — no ML / LLM."""
        g = StateGraph(AnalysisState)

        def ingest_with_error(_state):
            return {"errors": ["rejected url"]}

        def ingest_clean(_state):
            return {"audio_path": "/tmp/fake.wav"}

        def validate_no_op(_state):
            return {}

        def features_no_op(state):
            return {"key": "C major", "tempo": 120.0, "chords": []}

        # Two flavours of ingest so the same mini-graph can be reused.
        g.add_node("ingest", ingest_with_error)
        g.add_node("validate_audio", validate_no_op)
        g.add_node("features", features_no_op)
        g.add_node("roman", lambda s: {"roman": None})

        g.add_edge(START, "ingest")
        g.add_conditional_edges(
            "ingest", has_errors_route,
            {"fail": END, "ok": "validate_audio"},
        )
        g.add_conditional_edges(
            "validate_audio", has_errors_route,
            {"fail": END, "ok": "features"},
        )
        g.add_conditional_edges(
            "features", should_retry,
            {"retry": "features", "fail": END, "ok": "roman"},
        )
        g.add_edge("roman", END)
        return g.compile()

    def test_ingest_error_terminates_without_looping(self):
        """The crashing scenario — a 10007-iter recursion limit shouldn't fire."""
        graph = self._build_mini_graph()
        # invoke with a fresh state; ingest sets errors and we should END.
        result = graph.invoke({"errors": [], "retries": 0})
        assert result.get("errors") == ["rejected url"]
        # Features never ran, so neither ``key`` nor ``roman`` were populated.
        assert "key" not in result
        assert "roman" not in result


class TestValidateErrorRouting:
    def test_validate_error_terminates_without_looping(self):
        """If ``validate_audio`` injects errors after ingest succeeds, end fast."""
        g = StateGraph(AnalysisState)

        def ingest_clean(_state):
            return {"audio_path": "/tmp/fake.wav"}

        def validate_with_error(_state):
            return {"errors": ["empty file"]}

        def features_no_op(state):  # pragma: no cover — should never run
            return {"key": "C major"}

        g.add_node("ingest", ingest_clean)
        g.add_node("validate_audio", validate_with_error)
        g.add_node("features", features_no_op)
        g.add_edge(START, "ingest")
        g.add_conditional_edges(
            "ingest", has_errors_route,
            {"fail": END, "ok": "validate_audio"},
        )
        g.add_conditional_edges(
            "validate_audio", has_errors_route,
            {"fail": END, "ok": "features"},
        )
        g.add_edge("features", END)
        graph = g.compile()

        result = graph.invoke({"errors": [], "retries": 0})
        assert result.get("errors") == ["empty file"]
        assert "key" not in result, "features_node should not have executed"


class TestProductionGraphTerminatesOnBadInput:
    """End-to-end against the *real* production graph (Plan 3 live-test report 2).

    The mini graphs above test the routing predicates in isolation. This
    test wires up the *actual* ingest_node, validate_audio_node, features_node
    etc. — the same nodes the worker runs — so any future regression in the
    real graph (e.g., someone removes a conditional edge) gets caught.
    """

    def _build_production_graph(self):
        """Recreate the production graph but with an in-memory checkpointer
        so we don't touch Mongo and so each test gets a fresh graph instance."""
        from langgraph.checkpoint.memory import MemorySaver

        from backend.graph.graph import build_graph
        return build_graph(MemorySaver())

    def test_local_path_typed_as_url_terminates_fast(self):
        """Live report scenario: user typed a file path into the YouTube URL field.

        The expected outcome is that ``ingest_node`` rejects the URL (no
        ``http://`` scheme) and ``has_errors_route`` immediately ends the
        pipeline. If this test ever runs into LangGraph's recursion ceiling,
        someone has reintroduced the infinite loop.
        """
        import asyncio

        graph = self._build_production_graph()

        state = {
            "youtube_url": "/home/janit.jain/Synesthesia/test.wav",
            "audio_path": None,
            "instrument": "guitar",
            "difficulty": "beginner",
            "errors": [],
            "retries": 0,
        }

        async def run():
            return await graph.ainvoke(
                state,
                config={
                    "configurable": {"thread_id": "test-bad-url"},
                    "recursion_limit": 50,  # tight cap — should terminate in ~1 step
                },
            )

        result = asyncio.run(run())

        # Should have terminated with errors set, no features computed.
        assert result.get("errors"), "expected errors from ingest_node URL rejection"
        assert any("Rejected URL" in e for e in result["errors"])
        # Features never ran, so these analytics keys should be absent.
        assert "chords" not in result or not result.get("chords")
        assert "key" not in result
        assert "roman" not in result or result.get("roman") is None

    def test_missing_audio_path_terminates_fast(self):
        """Worker invoked with neither URL nor an existing file path.

        Mirrors the case where the upload landed in a stale dir or was
        deleted between enqueue and consumption. Should terminate at ingest.
        """
        import asyncio

        graph = self._build_production_graph()

        state = {
            "youtube_url": None,
            "audio_path": "/nonexistent/path/missing.wav",
            "instrument": "guitar",
            "difficulty": "beginner",
            "errors": [],
            "retries": 0,
        }

        async def run():
            return await graph.ainvoke(
                state,
                config={
                    "configurable": {"thread_id": "test-missing-file"},
                    "recursion_limit": 50,
                },
            )

        result = asyncio.run(run())
        assert result.get("errors"), "expected errors from missing file"
        assert any("Audio file not found" in e or "validate_audio" in e
                    for e in result["errors"])


class TestFeaturesRetryStillBounded:
    def test_features_retries_at_most_twice_then_fails(self):
        """Repeat features failures should produce ``retries=2`` and stop."""
        g = StateGraph(AnalysisState)
        call_count = {"n": 0}

        def ingest_clean(_state):
            return {"audio_path": "/tmp/fake.wav"}

        def validate_no_op(_state):
            return {}

        def features_always_fails(state):
            call_count["n"] += 1
            return {"errors": ["boom"], "retries": state.get("retries", 0) + 1}

        g.add_node("ingest", ingest_clean)
        g.add_node("validate_audio", validate_no_op)
        g.add_node("features", features_always_fails)
        g.add_edge(START, "ingest")
        g.add_conditional_edges(
            "ingest", has_errors_route,
            {"fail": END, "ok": "validate_audio"},
        )
        g.add_conditional_edges(
            "validate_audio", has_errors_route,
            {"fail": END, "ok": "features"},
        )
        g.add_conditional_edges(
            "features", should_retry,
            {"retry": "features", "fail": END, "ok": END},
        )
        graph = g.compile()

        result = graph.invoke({"errors": [], "retries": 0})
        # max_retries=2 in should_retry → features runs up to 3 times in the
        # worst case (initial + 2 retries). Cap with a generous upper bound
        # so a future logic regression that re-introduces the infinite loop
        # fails this test fast.
        assert call_count["n"] <= 3
        assert result["retries"] == call_count["n"]
        assert result["errors"]
