"""G2.3 — theory prompt v2 includes cadence facts and grounding instructions."""

from __future__ import annotations

import pytest


class TestTheoryPromptV2:
    def test_v2_template_loads(self):
        """v2/theory.yaml must be loadable via the registry."""
        from backend.prompts.registry import load_template

        load_template.cache_clear()
        prompt = load_template("theory", version="v2")
        assert prompt is not None

    def test_v2_template_has_cadence_facts_variable(self):
        """The v2 prompt must contain the {cadence_facts} input variable."""
        from backend.prompts.registry import load_template

        load_template.cache_clear()
        prompt = load_template("theory", version="v2")
        assert "cadence_facts" in prompt.input_variables, (
            f"v2 prompt input_variables={prompt.input_variables!r}; "
            "expected 'cadence_facts' for deterministic grounding"
        )

    def test_v2_template_system_instructs_explain_not_invent(self):
        """The system message must tell the model to EXPLAIN the provided facts,
        not invent harmonic claims."""
        from backend.prompts.registry import load_template

        load_template.cache_clear()
        prompt = load_template("theory", version="v2")
        system_content = prompt.messages[0].prompt.template
        # Check for the grounding instruction keyword
        assert any(
            kw in system_content.lower()
            for kw in ("explain", "do not invent", "provided facts", "grounded")
        ), (
            "v2 system prompt must contain grounding instruction "
            f"(got: {system_content[:200]!r})"
        )

    def test_format_inputs_includes_cadence_facts_when_present(self):
        """_format_inputs must populate cadence_facts from roman.cadences (G1 contract)."""
        from backend.chains.theory_chain import _format_inputs
        from backend.schemas import ChordEvent, RomanAnalysis, SongAnalysis

        roman = RomanAnalysis(
            key="C major",
            progression=["I", "V", "vi", "IV"],
            function=["tonic", "dominant", "submediant", "subdominant"],
            cadences=[
                {"type": "PAC", "index": 4},
                {"type": "half", "index": 8},
            ],
        )

        song = SongAnalysis(
            duration=30.0,
            key="C major",
            tempo=120.0,
            chords=[ChordEvent(start=0.0, end=1.0, chord="C")],
            roman=roman,
        )
        result = _format_inputs(song)
        assert "cadence_facts" in result
        assert "PAC" in result["cadence_facts"]
        assert "half" in result["cadence_facts"]

    def test_format_inputs_cadence_facts_fallback_when_none(self):
        """_format_inputs must emit 'None detected' when roman.cadences is absent or empty."""
        from backend.chains.theory_chain import _format_inputs
        from backend.schemas import ChordEvent, RomanAnalysis, SongAnalysis

        roman = RomanAnalysis(
            key="C major",
            progression=["I", "V"],
            function=["tonic", "dominant"],
            # cadences defaults to empty list — simulate no cadences detected
        )
        song = SongAnalysis(
            duration=30.0,
            key="C major",
            tempo=120.0,
            chords=[ChordEvent(start=0.0, end=1.0, chord="C")],
            roman=roman,
        )
        result = _format_inputs(song)
        assert result["cadence_facts"] == "None detected"

    def test_theory_prompt_module_loads_latest_which_is_v3(self):
        """After Phase 4 G5, 'latest' must resolve to v3 (lexicographically highest)."""
        from backend.prompts.registry import load_template

        load_template.cache_clear()
        prompt_latest = load_template("theory", version="latest")
        prompt_v3 = load_template("theory", version="v3")
        # Both should be structurally identical (same input_variables)
        assert set(prompt_latest.input_variables) == set(prompt_v3.input_variables)
        # v3 = v2 + the confidence-hedging variable
        prompt_v2 = load_template("theory", version="v2")
        assert set(prompt_v3.input_variables) - set(prompt_v2.input_variables) == {
            "key_confidence_note"
        }
