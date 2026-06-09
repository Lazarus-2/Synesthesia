"""G2.2 — build_theory_chain returns a TheoryExplanation, not a flat str."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestTheoryChainReturnsStructured:
    def test_chain_invoke_returns_theory_explanation_object(self):
        """build_theory_chain().invoke(SongAnalysis) must return a TheoryExplanation,
        not a str."""
        from langchain_core.runnables import RunnableLambda

        from backend.chains import theory_chain
        from backend.schemas import ChordEvent, SongAnalysis, TheoryExplanation

        expected = TheoryExplanation(
            key_summary="C major song.",
            function_explanation="Tonic, dominant.",
            pattern_name="I-V-vi-IV",
            notable_techniques=["modal mixture"],
            similar_song="Let It Be — Beatles",
        )

        with patch.object(
            theory_chain,
            "build_structured_llm",
            return_value=RunnableLambda(lambda _x: expected),
        ):
            chain = theory_chain.build_theory_chain()

        song = SongAnalysis(
            duration=30.0,
            key="C major",
            tempo=120.0,
            chords=[ChordEvent(start=0.0, end=1.0, chord="C")],
        )
        result = chain.invoke(song)

        assert isinstance(result, TheoryExplanation), (
            f"Expected TheoryExplanation, got {type(result)}"
        )
        assert result.key_summary == "C major song."
        assert result.pattern_name == "I-V-vi-IV"

    def test_chain_invoke_does_not_return_string(self):
        """Regression: the _flatten step must NOT be in the hot path."""
        from langchain_core.runnables import RunnableLambda

        from backend.chains import theory_chain
        from backend.schemas import ChordEvent, SongAnalysis, TheoryExplanation

        te = TheoryExplanation(
            key_summary="A minor.",
            function_explanation="Tonic.",
        )

        with patch.object(
            theory_chain,
            "build_structured_llm",
            return_value=RunnableLambda(lambda _x: te),
        ):
            chain = theory_chain.build_theory_chain()

        song = SongAnalysis(
            duration=10.0, key="A minor", tempo=90.0, chords=[]
        )
        result = chain.invoke(song)
        assert not isinstance(result, str), (
            "build_theory_chain must return a TheoryExplanation, not a flat string. "
            "_flatten should no longer be in the chain pipeline."
        )

    def test_to_text_helper_still_works(self):
        """The module-level to_text() utility must still render the Markdown."""
        from backend.chains.theory_chain import to_text
        from backend.schemas import TheoryExplanation

        te = TheoryExplanation(
            key_summary="G major.",
            function_explanation="Desc.",
            similar_song="Imagine — Lennon",
        )
        out = to_text(te)
        assert "G major" in out
        assert "Imagine" in out

    def test_flatten_kept_as_private_helper_not_removed(self):
        """_flatten must still exist (other tests / legacy code may reference it)
        but must not be wired into the chain's return type."""
        from backend.chains import theory_chain

        assert hasattr(theory_chain, "_flatten"), (
            "_flatten should be kept as a utility / back-compat helper, just "
            "removed from the chain pipeline."
        )


class TestTheoryChainSchemaUsesSchemasDotTheoryExplanation:
    def test_build_structured_llm_receives_schemas_theory_explanation(self):
        """theory_chain must pass schemas.TheoryExplanation (not the local copy)
        to build_structured_llm after G2.1 moves the class to schemas.py."""
        from langchain_core.runnables import RunnableLambda

        from backend.chains import theory_chain
        from backend.schemas import TheoryExplanation

        captured = []

        def _fake_structured(schema, temperature=0.2):
            captured.append(schema)
            return RunnableLambda(lambda _x: _x)

        with patch.object(theory_chain, "build_structured_llm", side_effect=_fake_structured):
            theory_chain.build_theory_chain()

        assert captured == [TheoryExplanation], (
            f"Expected build_structured_llm to receive schemas.TheoryExplanation; "
            f"got {captured}"
        )
