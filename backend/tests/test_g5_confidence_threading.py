"""Phase 4 G5 — key/tempo confidence threaded end-to-end.

state -> SongAnalysis -> SongAnalysisModel -> theory prompt v3 (hedging) ->
chat context -> AURA facts, plus analyzer_version dedup stamping (DEDUP-VER).
"""

from __future__ import annotations

from backend.config import ANALYZER_VERSION, get_settings
from backend.models import SongAnalysisModel
from backend.schemas import ChordEvent, SongAnalysis


def _chord(label: str, i: int = 0) -> ChordEvent:
    return ChordEvent(start=float(i), end=float(i + 1), chord=label, confidence=0.9, color="#fff")


def _analysis(**over) -> SongAnalysis:
    base = dict(
        duration=10.0,
        key="C major",
        tempo=120.0,
        chords=[_chord("C"), _chord("F", 1), _chord("G", 2)],
    )
    base.update(over)
    return SongAnalysis(**base)


class TestSchemaFields:
    def test_confidences_default_to_none_for_legacy_docs(self):
        a = _analysis()
        assert a.key_confidence is None
        assert a.tempo_confidence is None
        m = SongAnalysisModel(
            id="x", duration=1.0, key="C major", tempo=120.0, chords=[]
        )
        assert m.key_confidence is None
        assert m.tempo_confidence is None
        assert m.analyzer_version is None

    def test_confidences_round_trip(self):
        a = _analysis(key_confidence=0.83, tempo_confidence=0.91)
        dumped = a.model_dump()
        assert dumped["key_confidence"] == 0.83
        assert dumped["tempo_confidence"] == 0.91

    def test_analyzer_version_constant_is_set(self):
        assert isinstance(ANALYZER_VERSION, str) and ANALYZER_VERSION

    def test_settings_expose_confidence_thresholds(self):
        s = get_settings()
        assert 0.0 < s.key_confidence_low_threshold < 1.0
        assert 0.0 < s.tempo_confidence_low_threshold < 1.0


class TestStateToAnalysis:
    def test_song_analysis_from_state_threads_confidences(self):
        from backend.graph.nodes import _song_analysis_from_state

        state = {
            "key": "A minor",
            "key_confidence": 0.7,
            "tempo": 96.0,
            "tempo_confidence": 0.85,
            "chords": [_chord("Am")],
        }
        a = _song_analysis_from_state(state)
        assert a.key_confidence == 0.7
        assert a.tempo_confidence == 0.85


class TestTheoryPromptV3:
    def test_v3_template_loads_and_takes_confidence_note(self):
        from backend.prompts.registry import load_template

        prompt = load_template("theory", version="v3")
        assert "key_confidence_note" in prompt.input_variables

    def test_low_confidence_produces_hedging_note(self):
        from backend.chains.theory_chain import _format_inputs

        inputs = _format_inputs(_analysis(key_confidence=0.15))
        note = inputs["key_confidence_note"]
        assert "LOW" in note
        assert "hedge" in note.lower()

    def test_high_confidence_produces_plain_note(self):
        from backend.chains.theory_chain import _format_inputs

        inputs = _format_inputs(_analysis(key_confidence=0.92))
        note = inputs["key_confidence_note"]
        assert "LOW" not in note
        assert "92%" in note

    def test_missing_confidence_is_neutral(self):
        from backend.chains.theory_chain import _format_inputs

        inputs = _format_inputs(_analysis())
        assert "unknown" in inputs["key_confidence_note"].lower()

    def test_roman_progression_capped_at_32(self):
        from backend.chains.theory_chain import _format_inputs
        from backend.schemas import RomanAnalysis

        roman = RomanAnalysis(
            key="C major",
            progression=["I"] * 50,
            function=["tonic"] * 50,
            summary_progression=["I"],
            entries=[],
            cadences=[],
            modulations=[],
        )
        inputs = _format_inputs(_analysis(roman=roman))
        assert inputs["roman"].count("I") <= 32

    def test_modulations_surfaced_in_cadence_facts(self):
        from backend.chains.theory_chain import _format_inputs
        from backend.schemas import RomanAnalysis

        roman = RomanAnalysis(
            key="C major",
            progression=["I"],
            function=["tonic"],
            summary_progression=["I"],
            entries=[],
            cadences=[],
            modulations=[{"to_key": "G major", "at_index": 4}],
        )
        inputs = _format_inputs(_analysis(roman=roman))
        assert "G major" in inputs["cadence_facts"]


class TestChatContext:
    def test_context_mentions_confidence_when_present(self):
        from backend.chains.chat_chain import _format_analysis_context

        ctx = _format_analysis_context(
            {"key": "C major", "key_confidence": 0.82, "tempo": 120.0, "chords": []}
        )
        assert "82%" in ctx

    def test_low_confidence_adds_caveat(self):
        from backend.chains.chat_chain import _format_analysis_context

        ctx = _format_analysis_context(
            {"key": "C major", "key_confidence": 0.2, "tempo": 120.0, "chords": []}
        )
        assert "uncertain" in ctx.lower() or "low" in ctx.lower()

    def test_absent_confidence_keeps_legacy_format(self):
        from backend.chains.chat_chain import _format_analysis_context

        ctx = _format_analysis_context({"key": "C major", "tempo": 120.0, "chords": []})
        assert "confidence" not in ctx.lower()


class TestAuraFacts:
    def test_facts_block_includes_confidences(self):
        from backend.chains.aura_agent import _facts_block

        block = _facts_block(
            {
                "key": "C major",
                "key_confidence": 0.9,
                "tempo": 120.0,
                "tempo_confidence": 0.8,
                "status": "ok",
            }
        )
        assert "key_confidence: 90%" in block
        assert "tempo_confidence: 80%" in block

    def test_low_key_confidence_adds_caveat(self):
        from backend.chains.aura_agent import _facts_block

        block = _facts_block(
            {"key": "C major", "key_confidence": 0.1, "tempo": 120.0, "status": "ok"}
        )
        assert "key detection is uncertain" in block.lower()

    def test_absent_confidence_keeps_legacy_block(self):
        from backend.chains.aura_agent import _facts_block

        block = _facts_block({"key": "C major", "tempo": 120.0, "status": "ok"})
        assert "key_confidence" not in block
