"""G2.4 — theory_node writes a TheoryExplanation object, not a string."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_state(key="C major", tempo=120.0, chords=None, roman=None):
    from backend.schemas import RomanAnalysis

    return {
        "job_id": "test-job",
        "key": key,
        "tempo": tempo,
        "chords": chords or [],
        "beats": [],
        "sections": [],
        "roman": roman or RomanAnalysis(
            key=key, progression=["I", "V", "vi", "IV"],
            function=["tonic", "dominant", "submediant", "subdominant"],
        ),
        "errors": [],
    }


class TestTheoryNodeStructuredOutput:
    def test_theory_node_returns_theory_typed_key(self):
        """theory_node must write state key 'theory' (a TheoryExplanation), not just
        'theory_explanation' (a str)."""
        from langchain_core.runnables import RunnableLambda

        from backend.graph import nodes
        from backend.schemas import TheoryExplanation

        te = TheoryExplanation(
            key_summary="C major.",
            function_explanation="Tonic, dominant.",
        )

        with patch("backend.chains.theory_chain.build_theory_chain", return_value=RunnableLambda(lambda _x: te)):
            result = nodes.theory_node(_make_state())

        assert "theory" in result, (
            f"theory_node must write 'theory' key; got keys: {list(result.keys())}"
        )
        assert isinstance(result["theory"], TheoryExplanation)
        assert result["theory"].key_summary == "C major."

    def test_theory_node_also_writes_theory_explanation_for_back_compat(self):
        """theory_node must also write theory_explanation=str for legacy consumers
        (AnalysisState.theory_explanation, tasks.py assembly)."""
        from langchain_core.runnables import RunnableLambda

        from backend.graph import nodes
        from backend.schemas import TheoryExplanation

        te = TheoryExplanation(
            key_summary="G major.",
            function_explanation="Dominant seventh.",
            pattern_name="Blues",
        )

        with patch("backend.chains.theory_chain.build_theory_chain", return_value=RunnableLambda(lambda _x: te)):
            result = nodes.theory_node(_make_state(key="G major"))

        assert "theory_explanation" in result
        assert isinstance(result["theory_explanation"], str)
        assert "G major" in result["theory_explanation"]
        assert "Blues" in result["theory_explanation"]

    def test_theory_node_offline_fallback_still_writes_str(self):
        """When the LLM call raises, theory_node must still write theory_explanation
        as a degraded str message (no change to offline path)."""
        from backend.graph import nodes

        with patch(
            "backend.chains.theory_chain.build_theory_chain",
            side_effect=RuntimeError("LLM offline"),
        ):
            result = nodes.theory_node(_make_state())

        # Offline path writes a string, not a TheoryExplanation
        assert "theory_explanation" in result
        assert isinstance(result["theory_explanation"], str)
        # Offline path must NOT crash — 'theory' key may be absent or None
        assert result.get("theory") is None or isinstance(result["theory"], type(None))

    def test_analysis_state_accepts_theory_typed_key(self):
        """AnalysisState TypedDict must declare a 'theory' field of type
        TheoryExplanation | None."""
        from backend.graph.state import AnalysisState
        from backend.schemas import TheoryExplanation

        hints = AnalysisState.__annotations__
        assert "theory" in hints, (
            f"AnalysisState must declare 'theory'; got keys: {list(hints.keys())}"
        )
