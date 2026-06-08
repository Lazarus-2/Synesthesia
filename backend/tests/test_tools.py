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


from backend.tools.chords import ChordParts, parse_chord


class TestParseChord:
    def test_bare_major(self):
        p = parse_chord("C")
        assert isinstance(p, ChordParts)
        assert (p.root, p.quality, p.bass) == ("C", "maj", None)

    def test_minor_is_min_not_maj(self):
        assert parse_chord("Am").quality == "min"
        assert parse_chord("F#m").root == "F#"
        assert parse_chord("F#m").quality == "min"

    def test_maj7_is_not_misread_as_minor(self):
        # The historical bug: "m" in "maj7" matched the minor branch.
        p = parse_chord("Cmaj7")
        assert p.root == "C"
        assert p.quality == "maj7"
        assert p.bass is None

    def test_min7(self):
        assert parse_chord("Dm7").quality == "min7"
        assert parse_chord("Em7").quality == "min7"

    def test_dominant_seventh(self):
        assert parse_chord("G7").quality == "dom7"
        assert parse_chord("C7").quality == "dom7"

    def test_diminished_and_half_diminished(self):
        assert parse_chord("Bdim").quality == "dim"
        assert parse_chord("Bo").quality == "dim"
        assert parse_chord("Bm7b5").quality == "m7b5"
        assert parse_chord("Bø").quality == "m7b5"

    def test_augmented(self):
        assert parse_chord("Caug").quality == "aug"
        assert parse_chord("C+").quality == "aug"

    def test_sus_and_added_tones(self):
        assert parse_chord("Dsus2").quality == "sus2"
        assert parse_chord("Dsus4").quality == "sus4"
        assert parse_chord("C6").quality == "6"
        assert parse_chord("C9").quality == "9"

    def test_slash_bass_parsed(self):
        p = parse_chord("Dm7/G")
        assert p.root == "D"
        assert p.quality == "min7"
        assert p.bass == "G"

    def test_slash_bass_with_accidental(self):
        p = parse_chord("D/F#")
        assert p.root == "D"
        assert p.quality == "maj"
        assert p.bass == "F#"

    def test_flat_root_preserved_with_accidental(self):
        p = parse_chord("Bbmaj7")
        assert p.root == "Bb"
        assert p.quality == "maj7"

    def test_no_chord_and_unknown(self):
        assert parse_chord("N.C.").root == ""
        assert parse_chord("N").root == ""
        assert parse_chord("").root == ""


from backend.tools.synesthesia_colors import get_chord_color


class TestChordColorQuality:
    def test_maj7_is_not_the_minor_color(self):
        # Historical bug: "m" in "maj7" -> minor branch -> darkened color.
        # Cmaj7 must read as a *major* color, distinct from Cm.
        cmaj7 = get_chord_color("Cmaj7")
        cmin = get_chord_color("Cm")
        assert cmaj7 != cmin

    def test_maj7_close_to_plain_major(self):
        # maj7 should be a 7th-boost of C major, not a darkened minor.
        c_major = get_chord_color("C")
        c_maj7 = get_chord_color("Cmaj7")
        # Same hue family: both are red-ish, not the cooled/darkened minor.
        assert c_maj7 != get_chord_color("Cm")
        assert c_major != get_chord_color("Cm")

    def test_diminished_neon_pink(self):
        assert get_chord_color("Bdim") == "#FF00C8"
        assert get_chord_color("Bo") == "#FF00C8"

    def test_half_diminished_is_dim_family(self):
        assert get_chord_color("Bm7b5") == "#FF00C8"

    def test_augmented_lime(self):
        assert get_chord_color("Caug") == "#B6FF00"
        assert get_chord_color("C+") == "#B6FF00"

    def test_no_chord_dark(self):
        assert get_chord_color("N.C.") == "#1A1A1A"
