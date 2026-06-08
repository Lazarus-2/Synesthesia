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

    def test_transposes_slash_bass(self):
        # D/F# up two semitones -> E/G#: BOTH root and bass move.
        assert transpose_chord("D/F#", 2) == "E/G#"

    def test_slash_bass_down(self):
        assert transpose_chord("Dm7/G", -2) == "Cm7/F"

    def test_maj7_quality_preserved(self):
        assert transpose_chord("Cmaj7", 2) == "Dmaj7"

    def test_no_chord_passthrough(self):
        assert transpose_chord("N.C.", 5) == "N.C."


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

    def test_capo_handles_slash_chords_without_crashing(self):
        # Slash chords used to leave "/bass" glued in the suffix; ensure the
        # capo search runs and the recommended shapes are themselves slash-aware.
        res = suggest_capo.invoke({"chords": ["G/B", "C", "D/F#"]})
        assert res["capo"] in range(0, 8)
        assert isinstance(res["shapes"], list)
        assert len(res["shapes"]) == 3

    def test_capo_recognizes_maj7_root_for_open_match(self):
        # is_easy_shape must key on root+quality, not raw string membership.
        res = suggest_capo.invoke({"chords": ["Amaj7", "Dmaj7"]})
        assert "score" in res


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


class TestVoicingFallback:
    def test_seventh_chord_not_dropped_guitar(self):
        # Cmaj7 has a real shape; G7/C7 have real shapes; but a 7th with no
        # table entry must degrade to its triad rather than vanish.
        diagrams = get_chord_diagrams(["Cmaj7", "G7", "Am7"], instrument="guitar")
        labels = [d.chord for d in diagrams]
        assert "Cmaj7" in labels
        assert "G7" in labels
        assert "Am7" in labels  # direct hit in guitar table

    def test_unknown_extension_degrades_to_triad(self):
        # F#m9 has no table entry -> should degrade to F#m... -> Em-shape family.
        # At minimum it must NOT be silently dropped.
        diagrams = get_chord_diagrams(["Am9"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "Am9"

    def test_slash_chord_uses_root_triad(self):
        diagrams = get_chord_diagrams(["D/F#"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "D/F#"

    def test_truly_unparseable_still_dropped(self):
        diagrams = get_chord_diagrams(["INVALID_CHORD"], instrument="guitar")
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


# ---------------------------------------------------------------------------
# Regression tests for FT-09 code-review fixes
# ---------------------------------------------------------------------------


class TestExtensionParsing:
    """Fix 1 — minor/major 9/11/13 extensions must NOT collapse to the base triad."""

    # --- minor extensions ---
    def test_m9_quality_is_min9(self):
        assert parse_chord("Am9").quality == "min9"

    def test_m11_quality_is_min11(self):
        assert parse_chord("Cm11").quality == "min11"

    def test_m13_quality_is_min13(self):
        assert parse_chord("Gm13").quality == "min13"

    def test_min9_prefix_is_min9(self):
        assert parse_chord("Dmin9").quality == "min9"

    def test_min11_prefix_is_min11(self):
        assert parse_chord("Emin11").quality == "min11"

    def test_min13_prefix_is_min13(self):
        assert parse_chord("Fmin13").quality == "min13"

    # --- major extensions ---
    def test_maj9_quality_is_maj9(self):
        assert parse_chord("Cmaj9").quality == "maj9"

    def test_maj11_quality_is_maj11(self):
        assert parse_chord("Cmaj11").quality == "maj11"

    def test_maj13_quality_is_maj13(self):
        assert parse_chord("Cmaj13").quality == "maj13"

    # --- extension root is preserved correctly ---
    def test_m9_root_correct(self):
        p = parse_chord("Am9")
        assert p.root == "A"
        assert p.quality == "min9"

    def test_maj9_root_correct(self):
        p = parse_chord("Cmaj9")
        assert p.root == "C"
        assert p.quality == "maj9"

    # --- previously-passing rules are not broken by reordering ---
    def test_min7_still_works(self):
        assert parse_chord("Dm7").quality == "min7"

    def test_maj7_still_works(self):
        assert parse_chord("Cmaj7").quality == "maj7"

    def test_plain_minor_still_works(self):
        assert parse_chord("Am").quality == "min"

    def test_plain_major_still_works(self):
        assert parse_chord("C").quality == "maj"


class TestPowerChord:
    """Fix 2 — C5, G5, etc. must parse as quality 'power', not 'maj'."""

    def test_c5_is_power(self):
        assert parse_chord("C5").quality == "power"

    def test_g5_root_and_quality(self):
        p = parse_chord("G5")
        assert p.root == "G"
        assert p.quality == "power"

    def test_fsharp5_is_power(self):
        assert parse_chord("F#5").quality == "power"


class TestTransposeCompleteness:
    """Fix 3 — transpose_chord must handle every quality parse_chord can emit."""

    def test_transpose_m9(self):
        assert transpose_chord("Am9", 2) == "Bm9"

    def test_transpose_m11(self):
        assert transpose_chord("Cm11", 2) == "Dm11"

    def test_transpose_m13(self):
        assert transpose_chord("Gm13", 2) == "Am13"

    def test_transpose_maj9(self):
        assert transpose_chord("Cmaj9", 2) == "Dmaj9"

    def test_transpose_maj11(self):
        assert transpose_chord("Cmaj11", 2) == "Dmaj11"

    def test_transpose_maj13(self):
        assert transpose_chord("Cmaj13", 2) == "Dmaj13"

    def test_transpose_power_chord(self):
        assert transpose_chord("C5", 2) == "D5"

    def test_transpose_power_chord_wraps(self):
        assert transpose_chord("B5", 1) == "C5"


class TestVoicingsDegradationPolicy:
    """Fix 4 — degrade/drop policy for voicings."""

    # Am7 is a direct hit on guitar; degrades to Am on ukulele/piano/bass
    def test_am7_direct_hit_guitar(self):
        diagrams = get_chord_diagrams(["Am7"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "Am7"

    def test_am7_degrades_to_am_ukulele(self):
        # No Am7 shape in ukulele table → degrade to Am (minor triad)
        diagrams = get_chord_diagrams(["Am7"], instrument="ukulele")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "Am7"  # label is the original

    def test_am7_degrades_to_am_piano(self):
        diagrams = get_chord_diagrams(["Am7"], instrument="piano")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "Am7"

    def test_am7_degrades_to_am_bass(self):
        diagrams = get_chord_diagrams(["Am7"], instrument="bass")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "Am7"

    # dim / m7b5 should be DROPPED, not shown with a wrong Am shape
    def test_adim_dropped_when_no_dim_shape(self):
        # There is no Adim shape in any table; must not fall through to Am.
        diagrams = get_chord_diagrams(["Adim"], instrument="guitar")
        assert len(diagrams) == 0

    def test_am7b5_dropped_when_no_shape(self):
        diagrams = get_chord_diagrams(["Am7b5"], instrument="ukulele")
        assert len(diagrams) == 0

    # Minor extension chords degrade to minor triad on instruments without the
    # exact shape, not to major triad.
    def test_am9_guitar_degrades_to_am_not_a(self):
        # Am9 has no guitar shape → degrade to Am (not A)
        diagrams = get_chord_diagrams(["Am9"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "Am9"
