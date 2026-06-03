"""End-to-end pipeline tests (Plan 3 live-test report 2 follow-up).

Each test exercises the **real** production graph (not stub nodes) so
regressions in node logic are caught. LLM-touching nodes (theory,
instrument) are short-circuited by patching ``build_*_chain`` because we
don't want to depend on a live Ollama for CI; the deterministic ML nodes
(features, roman, similarity, structure) still run for real against the
synthetic-audio fixture from :mod:`tests.conftest`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("librosa")


def _build_graph_no_llm():
    """Build the production graph against MemorySaver, with LLM nodes stubbed.

    The instrument chain and theory chain need ``build_llm`` which would
    try to reach the configured provider (Ollama by default). The pipeline
    catches their exceptions and substitutes fallbacks, but we'd rather
    skip the network call entirely in CI.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from backend.graph.graph import build_graph

    return build_graph(MemorySaver())


class TestFullPipelineWithSyntheticAudio:
    """Real graph + real synthetic_song + LLM nodes mocked to safe fallbacks."""

    @pytest.fixture(autouse=True)
    def _stub_llm_chains(self):
        """Force theory + instrument LLM chains to raise so the node catch
        clauses run. This keeps the test offline-deterministic."""
        with (
            patch(
                "backend.chains.theory_chain.build_theory_chain",
                side_effect=RuntimeError("LLM stubbed for test"),
            ),
            patch(
                "backend.chains.instrument_chain.build_instrument_chain",
                side_effect=RuntimeError("LLM stubbed for test"),
            ),
        ):
            yield

    def test_synthetic_audio_produces_analysis_with_chords_and_key(
        self,
        synthetic_song: Path,
    ):
        """A clean run with valid audio should populate key/tempo/chords/roman."""
        graph = _build_graph_no_llm()

        initial = {
            "audio_path": str(synthetic_song),
            "youtube_url": None,
            "instrument": "guitar",
            "difficulty": "beginner",
            "errors": [],
            "retries": 0,
        }

        async def run():
            return await graph.ainvoke(
                initial,
                config={
                    "configurable": {"thread_id": "e2e-synthetic"},
                    "recursion_limit": 50,
                },
            )

        result = asyncio.run(run())

        # Pipeline reached the end without errors.
        assert not result.get("errors"), f"unexpected pipeline errors: {result.get('errors')}"

        # Features ran: we got a key/tempo and at least some chord events.
        assert "key" in result and result["key"], "key estimation should populate"
        assert "tempo" in result and result["tempo"] > 0, "tempo should be positive"
        assert isinstance(result.get("chords"), list)
        # The synthetic song is constructed from chord-progression tones so we
        # *should* detect at least one chord. If chord detection is bypassed
        # for any reason this catches it.
        assert len(result["chords"]) > 0, "should detect at least one chord"

        # Roman analysis ran (uses ``chords`` and ``key``).
        assert "roman" in result
        assert result["roman"] is None or hasattr(result["roman"], "progression")

        # Theory/instrument nodes ran but were caught — their fallback text/
        # guides should be present rather than the keys missing. The fallback
        # message was made user-friendly in the live-test review pass; we
        # assert on a stable marker phrase rather than the exact prose.
        assert "theory_explanation" in result
        theory_text = result.get("theory_explanation") or ""
        assert (
            "deterministic part of the analysis" in theory_text
            or "AI commentary engine is offline" in theory_text
        ), f"unexpected theory fallback: {theory_text[:200]!r}"
        assert result.get("instrument_guide") is not None
        assert "guitar" == result["instrument_guide"].instrument

        # Stems node runs in parallel but returns {} when demucs is missing
        # in the test env — should be present as either {} or a dict.
        assert isinstance(result.get("stems", {}), dict)

    def test_synthetic_audio_run_is_bounded_in_steps(
        self,
        synthetic_song: Path,
    ):
        """A clean run must not approach LangGraph's recursion limit.

        Setting ``recursion_limit=15`` is well below the real default (10007)
        and gives plenty of headroom for the genuine graph (ingest → validate
        → features → roman → 4×parallel → END = ~8 steps).
        """
        graph = _build_graph_no_llm()

        async def run():
            return await graph.ainvoke(
                {
                    "audio_path": str(synthetic_song),
                    "errors": [],
                    "retries": 0,
                    "instrument": "guitar",
                    "difficulty": "beginner",
                },
                config={
                    "configurable": {"thread_id": "e2e-bounded"},
                    "recursion_limit": 15,
                },
            )

        # Should not raise; if recursion_limit is hit, asyncio.run will raise
        # ``GraphRecursionError`` which fails the test loudly.
        result = asyncio.run(run())
        assert result is not None
