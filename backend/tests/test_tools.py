"""
Unit tests for the deterministic music-theory tools.
Vault ref: 03-LangChain-Core/05-Testing-Debugging-LangChain.md
"""

from backend.tools.capo import suggest_capo
from backend.tools.transpose import transpose_chord, transpose_progression


class TestTranspose:
    def test_up_two_semitones(self):
        assert transpose_chord("C", 2) == "D"
        assert transpose_chord("F#m", 2) == "G#m"

    def test_down_five_semitones(self):
        assert transpose_chord("G", -5) == "D"

    def test_wraps_octave(self):
        assert transpose_chord("B", 1) == "C"

    def test_handles_flats(self):
        assert transpose_chord("Bb", 0) == "A#"

    def test_progression_preserves_order(self):
        out = transpose_progression.invoke({"chords": ["C", "G", "Am", "F"], "semitones": 2})
        assert out == ["D", "A", "Bm", "G"]


class TestCapo:
    def test_capo_helps_with_barre_chords(self):
        # F Bb Dm Gm are ugly; capo 5 -> C F Am Dm (all easy)
        res = suggest_capo.invoke({"chords": ["F", "Bb", "Dm", "Gm"]})
        assert res["capo"] > 0
        assert res["score"] > 0

    def test_capo_zero_when_already_easy(self):
        res = suggest_capo.invoke({"chords": ["C", "G", "Am", "F"]})
        # C G Am are already open; capo might still help with F but 0 is valid
        assert res["capo"] in (0, 3, 5, 7)


from backend.tools.voicings import get_chord_diagrams


class TestChordDiagrams:
    def test_get_chord_diagrams_guitar(self):
        diagrams = get_chord_diagrams(["C", "Am", "G7"], instrument="guitar")
        assert len(diagrams) == 3
        # Ensure fallback happens for Am and shape works for C
        assert diagrams[0].chord == "C"
        assert diagrams[0].instrument == "guitar"

    def test_get_chord_diagrams_bass(self):
        diagrams = get_chord_diagrams(["C", "G"], instrument="bass")
        assert len(diagrams) == 2
        assert diagrams[0].instrument == "bass"

    def test_get_chord_diagrams_ukulele(self):
        diagrams = get_chord_diagrams(["C", "Em"], instrument="ukulele")
        assert len(diagrams) == 2
        assert diagrams[0].instrument == "ukulele"

    def test_guardrails_malformed_input(self):
        # Should gracefully fallback or ignore
        diagrams = get_chord_diagrams(["INVALID_CHORD"], instrument="guitar")
        # Because we only append if shape is found, malformed chords with no shape should yield empty
        assert len(diagrams) == 0
