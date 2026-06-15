"""Phase 5 G3 — surface time_signature + sections into LLM grounding.

The detected meter (G2) and song sections should reach the theory prompt,
the chat context, and the AURA facts block so commentary can reference the
song's structure and meter. Sections also gain a confidence.
"""

from __future__ import annotations

from backend.schemas import ChordEvent, SongAnalysis, SongSection


def _chord(label: str, i: int = 0) -> ChordEvent:
    return ChordEvent(start=float(i), end=float(i + 1), chord=label, confidence=0.9, color="#fff")


def _analysis(**over) -> SongAnalysis:
    base = dict(
        duration=12.0,
        key="C major",
        tempo=120.0,
        time_signature="3/4",
        chords=[_chord("C"), _chord("F", 1), _chord("G", 2)],
        sections=[
            SongSection(name="Intro", start=0.0, end=4.0),
            SongSection(name="Verse", start=4.0, end=12.0),
        ],
    )
    base.update(over)
    return SongAnalysis(**base)


class TestSongSectionConfidence:
    def test_section_has_confidence_default(self):
        s = SongSection(name="Verse", start=0.0, end=4.0)
        assert s.confidence == 1.0

    def test_section_confidence_bounded(self):
        s = SongSection(name="Chorus", start=0.0, end=4.0, confidence=0.42)
        assert s.confidence == 0.42


class TestChatGrounding:
    def test_context_includes_time_signature(self):
        from backend.chains.chat_chain import _format_analysis_context

        ctx = _format_analysis_context(_analysis().model_dump())
        assert "3/4" in ctx

    def test_context_includes_section_names(self):
        from backend.chains.chat_chain import _format_analysis_context

        ctx = _format_analysis_context(_analysis().model_dump())
        assert "Intro" in ctx and "Verse" in ctx

    def test_context_omits_meter_when_absent(self):
        from backend.chains.chat_chain import _format_analysis_context

        ctx = _format_analysis_context({"key": "C major", "tempo": 120.0, "chords": []})
        assert "Time signature" not in ctx


class TestAuraFactsMeter:
    def test_facts_include_time_signature(self):
        from backend.chains.aura_agent import _facts_block

        block = _facts_block(_analysis().model_dump())
        assert "time_signature: 3/4" in block

    def test_facts_still_include_sections(self):
        from backend.chains.aura_agent import _facts_block

        block = _facts_block(_analysis().model_dump())
        assert "Intro" in block and "Verse" in block


class TestTheoryPromptV4:
    def test_v4_loads_with_meter_and_sections(self):
        from backend.prompts.registry import load_template

        prompt = load_template("theory", version="v4")
        assert "time_signature" in prompt.input_variables
        assert "sections" in prompt.input_variables

    def test_latest_is_v4(self):
        from backend.prompts.registry import load_template

        load_template.cache_clear()
        latest = load_template("theory", version="latest")
        v4 = load_template("theory", version="v4")
        assert set(latest.input_variables) == set(v4.input_variables)

    def test_format_inputs_provides_meter_and_sections(self):
        from backend.chains.theory_chain import _format_inputs

        inputs = _format_inputs(_analysis())
        assert inputs["time_signature"] == "3/4"
        assert "Intro" in inputs["sections"] and "Verse" in inputs["sections"]

    def test_format_inputs_sections_empty_string_when_none(self):
        from backend.chains.theory_chain import _format_inputs

        inputs = _format_inputs(_analysis(sections=[]))
        assert inputs["sections"] in ("", "None detected")
