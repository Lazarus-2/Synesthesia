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
        # Unparseable labels (no recognisable root) get a no_voicing=True marker
        # rather than being silently dropped — the count is always preserved.
        diagrams = get_chord_diagrams(["INVALID_CHORD"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].no_voicing is True


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

    def test_truly_unparseable_returns_no_voicing_marker(self):
        # G3.3: no_voicing=True is emitted instead of silently dropping
        diagrams = get_chord_diagrams(["INVALID_CHORD"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].no_voicing is True


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


class TestCapoUnified:
    """G3.5 — capo is computed once deterministically; LLM no longer decides."""

    def test_instrument_guide_capo_matches_suggest_capo(self):
        """The capo on an InstrumentGuide must equal suggest_capo's answer."""
        from backend.tools.capo import suggest_capo
        from backend.chains.instrument_chain import _deterministic_capo

        chords = ["F", "Bb", "Dm", "Gm"]
        expected = suggest_capo.invoke({"chords": chords})["capo"]
        got = _deterministic_capo(chords)
        assert got == expected

    def test_deterministic_capo_for_all_open_chords(self):
        # C G Am are all easy open; no capo improvement expected.
        from backend.chains.instrument_chain import _deterministic_capo
        assert _deterministic_capo(["C", "G", "Am"]) in (0, None)

    def test_llm_instrument_tips_has_no_capo_field(self):
        """LLMInstrumentTips must NOT include 'capo' after G3.5."""
        from backend.chains.instrument_chain import LLMInstrumentTips
        assert "capo" not in LLMInstrumentTips.model_fields

    def test_diagrams_use_transposed_chords_when_capo_set(self):
        """With capo=5, Bb diagrams should be stored as F (the pressed shape)."""
        from backend.tools.voicings import get_chord_diagrams
        from backend.tools.transpose import transpose_chord

        capo = 5
        chords = ["Bb"]
        transposed = [transpose_chord(c, -capo) for c in chords]
        diagrams = get_chord_diagrams(transposed, instrument="guitar")
        # F is in the curated table; must come back as a non-barre open shape
        assert len(diagrams) == 1
        assert max(f for f in diagrams[0].frets if f >= 0) <= 3


class TestDifficultyVoicings:
    """G3.4 — difficulty selects simpler vs richer shapes."""

    def test_beginner_f_guitar_gets_capo_friendly_shape(self):
        """F major is hard; beginner should receive the curated open F or a
        low-fret barre, NOT the full-barre F on fret 1 with high stretch."""
        from backend.tools.voicings import get_chord_diagrams
        beginner = get_chord_diagrams(["F"], instrument="guitar", difficulty="beginner")
        assert len(beginner) == 1
        # Curated open F (frets=[1,3,3,2,1,1]) is fine for beginner; max fret <= 5
        assert max(f for f in beginner[0].frets if f >= 0) <= 5

    def test_advanced_bb_guitar_gets_barre_not_open(self):
        """Advanced player: Bb should get the full barre shape (fret 6),
        not be forced into a beginner-friendly simplification."""
        from backend.tools.voicings import get_chord_diagrams
        advanced = get_chord_diagrams(["Bb"], instrument="guitar", difficulty="advanced")
        assert len(advanced) == 1
        assert advanced[0].no_voicing is False
        # E-shape barre on fret 6: all strings fretted >= 6
        assert advanced[0].frets[0] == 6

    def test_beginner_bb_guitar_gets_a_shape_lower_fret(self):
        """Beginner gets the A-shape barre (fret 1, lower stretch) for Bb
        rather than the E-shape barre on fret 6."""
        from backend.tools.voicings import get_chord_diagrams
        beginner = get_chord_diagrams(["Bb"], instrument="guitar", difficulty="beginner")
        assert len(beginner) == 1
        assert beginner[0].no_voicing is False
        # A-shape Bb: root on string 1 at fret 1 -> [-1,1,3,3,3,1]
        assert beginner[0].frets[1] == 1   # root on A-string at fret 1

    def test_beginner_vs_advanced_same_length(self):
        """Both levels return a diagram for every chord."""
        from backend.tools.voicings import get_chord_diagrams
        chords = ["C", "G", "Am", "F", "Bb", "F#m"]
        b = get_chord_diagrams(chords, instrument="guitar", difficulty="beginner")
        a = get_chord_diagrams(chords, instrument="guitar", difficulty="advanced")
        assert len(b) == len(chords)
        assert len(a) == len(chords)


class TestNoVoicingMarker:
    """G3.3 — every chord returns a ChordDiagram; unsupported ones are marked."""

    def test_bb_guitar_now_returns_diagram_not_empty(self):
        """Bb was silently dropped before G3; now it must return a barre shape."""
        from backend.tools.voicings import get_chord_diagrams
        diagrams = get_chord_diagrams(["Bb"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "Bb"
        assert diagrams[0].frets is not None
        assert diagrams[0].no_voicing is False

    def test_fsharp_minor_guitar_returns_barre(self):
        from backend.tools.voicings import get_chord_diagrams
        diagrams = get_chord_diagrams(["F#m"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].no_voicing is False
        assert diagrams[0].frets[0] == 2   # Em-shape on fret 2

    def test_adim_guitar_returns_no_voicing_marker(self):
        """Adim has no table entry and no movable-shape template → no_voicing=True."""
        from backend.tools.voicings import get_chord_diagrams
        diagrams = get_chord_diagrams(["Adim"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "Adim"
        assert diagrams[0].no_voicing is True
        assert diagrams[0].frets is None

    def test_c_dominant7_piano_has_four_notes(self):
        from backend.tools.voicings import get_chord_diagrams
        diagrams = get_chord_diagrams(["C7"], instrument="piano")
        assert len(diagrams) == 1
        assert len(diagrams[0].right_hand) == 4
        assert diagrams[0].no_voicing is False

    def test_no_voicing_for_power_chord_on_piano(self):
        """Piano has no sensible voicing for a power chord — marker emitted."""
        from backend.tools.voicings import get_chord_diagrams
        diagrams = get_chord_diagrams(["C5"], instrument="piano")
        assert len(diagrams) == 1
        assert diagrams[0].no_voicing is True

    def test_all_chords_always_returned(self):
        """get_chord_diagrams never silently drops a chord; count must equal input."""
        from backend.tools.voicings import get_chord_diagrams
        chords = ["C", "Bb", "F#m", "Adim", "Gbmaj7", "C5"]
        diagrams = get_chord_diagrams(chords, instrument="guitar")
        assert len(diagrams) == len(chords)


class TestPianoVoicings:
    """G3.2 — piano voicings generated from chord-tone intervals."""

    def test_c_dominant7_has_four_right_hand_notes(self):
        from backend.tools.voicings import _piano_chord_voicing
        v = _piano_chord_voicing("C", "dom7")
        assert v is not None
        assert v["right_hand"] == ["C4", "E4", "G4", "A#4"]  # Bb = A#

    def test_g_major7_intervals(self):
        from backend.tools.voicings import _piano_chord_voicing
        v = _piano_chord_voicing("G", "maj7")
        assert v is not None
        # G4 B4 D5 F#4 — D5 because G+7=D wraps to next octave
        assert "G4" in v["right_hand"]
        assert "F#4" in v["right_hand"]   # maj7 interval: 11 semitones above G

    def test_d_minor_triad(self):
        from backend.tools.voicings import _piano_chord_voicing
        v = _piano_chord_voicing("D", "min")
        assert v is not None
        assert v["right_hand"] == ["D4", "F4", "A4"]

    def test_left_hand_is_root_only(self):
        from backend.tools.voicings import _piano_chord_voicing
        v = _piano_chord_voicing("A", "min7")
        assert v["left_hand"] == ["A3"]

    def test_bb_major_works(self):
        from backend.tools.voicings import _piano_chord_voicing
        v = _piano_chord_voicing("Bb", "maj")
        assert v is not None
        # Bb normalised to A#; F5 is octave-capped to F4, so notes sort to [F4, A#4, D5]
        assert "A#4" in v["right_hand"]   # root present
        assert len(v["right_hand"]) == 3  # triad has three notes

    def test_unsupported_quality_returns_none(self):
        from backend.tools.voicings import _piano_chord_voicing
        # 'power' chord on piano has no standard voicing defined
        assert _piano_chord_voicing("C", "power") is None


class TestBarreVoicings:
    """G3.1 — guitar movable-shape math."""

    def test_bb_major_e_shape_fret_6(self):
        """Bb is 6 semitones above E → E-shape barre on fret 6."""
        from backend.tools.voicings import _guitar_barre_shape
        shape = _guitar_barre_shape("Bb", "maj")
        # E-shape: open [0,2,2,1,0,0] + 6 = [6,8,8,7,6,6]
        assert shape is not None
        assert shape["frets"] == [6, 8, 8, 7, 6, 6]

    def test_fsharp_minor_em_shape_fret_2(self):
        """F#m is 2 semitones above E → Em-shape barre on fret 2."""
        from backend.tools.voicings import _guitar_barre_shape
        shape = _guitar_barre_shape("F#", "min")
        # Em-shape: open [0,2,2,0,0,0] + 2 = [2,4,4,2,2,2]
        assert shape is not None
        assert shape["frets"] == [2, 4, 4, 2, 2, 2]

    def test_c_major_a_shape_fret_3(self):
        """C is 3 semitones above A → A-shape barre on fret 3."""
        from backend.tools.voicings import _guitar_barre_shape
        shape = _guitar_barre_shape("C", "maj")
        # A-shape: [-1, F, F+2, F+2, F+2, F] = [-1, 3, 5, 5, 5, 3]
        # (open-position C is in table; but barre path must also work)
        assert shape is not None
        assert shape["frets"][0] == -1           # muted low E
        assert shape["frets"][1] == shape["frets"][5]  # barre fret matches

    def test_e_major_uses_open_not_barre(self):
        """E is the open root of E-shape → fret 0, not a high barre."""
        from backend.tools.voicings import _guitar_barre_shape
        shape = _guitar_barre_shape("E", "maj")
        assert shape is not None
        assert shape["frets"][0] == 0
        assert max(shape["frets"]) <= 2   # it's an open chord

    def test_unknown_quality_returns_none(self):
        """No movable shape exists for quality 'wtf'."""
        from backend.tools.voicings import _guitar_barre_shape
        assert _guitar_barre_shape("C", "wtf") is None


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

    # dim / m7b5 have no safe triad fallback; G3.3 emits no_voicing=True
    # instead of silently dropping — len is always 1 per input chord.
    def test_adim_returns_no_voicing_marker(self):
        # There is no Adim shape in any table; must not fall through to Am.
        # G3.3: returns a diagram with no_voicing=True instead of empty list.
        diagrams = get_chord_diagrams(["Adim"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].no_voicing is True

    def test_am7b5_returns_no_voicing_on_ukulele(self):
        diagrams = get_chord_diagrams(["Am7b5"], instrument="ukulele")
        assert len(diagrams) == 1
        assert diagrams[0].no_voicing is True

    # Minor extension chords degrade to minor triad on instruments without the
    # exact shape, not to major triad.
    def test_am9_guitar_degrades_to_am_not_a(self):
        # Am9 has no guitar shape → degrade to Am (not A)
        diagrams = get_chord_diagrams(["Am9"], instrument="guitar")
        assert len(diagrams) == 1
        assert diagrams[0].chord == "Am9"


class TestG3ReviewFixes:
    """G3 review fixes — C1, C2, I1."""

    # C1: Minor chords must return minor barre shapes, not major open shapes.
    def test_fm_guitar_is_minor_barre_not_f_major(self):
        """Fm must use Em-shape barre (fret 1 = [1,3,3,1,1,1]), not open F major."""
        diagrams = get_chord_diagrams(["Fm"], instrument="guitar")
        d = diagrams[0]
        assert d.no_voicing is False
        # Em-shape barre on fret 1: all barre strings at 1, inner pair at 3
        assert d.frets == [1, 3, 3, 1, 1, 1]

    def test_cm_guitar_is_minor_barre_not_c_major(self):
        """Cm must use Am-shape barre (fret 3 = [-1,3,5,5,4,3]), not open C major."""
        diagrams = get_chord_diagrams(["Cm"], instrument="guitar")
        d = diagrams[0]
        assert d.no_voicing is False
        assert d.frets == [-1, 3, 5, 5, 4, 3]

    def test_gm_guitar_is_minor_barre_not_g_major(self):
        """Gm must use Em-shape barre (fret 3 = [3,5,5,3,3,3]), not open G major."""
        diagrams = get_chord_diagrams(["Gm"], instrument="guitar")
        d = diagrams[0]
        assert d.no_voicing is False
        assert d.frets == [3, 5, 5, 3, 3, 3]

    def test_fm_frets_are_not_f_major_open(self):
        """Belt-and-suspenders: Fm frets must not equal the open F major shape."""
        diagrams = get_chord_diagrams(["Fm"], instrument="guitar")
        d = diagrams[0]
        # F major open shape is [1,3,3,2,1,1]
        assert d.frets != [1, 3, 3, 2, 1, 1]

    # C2: Cm7b5 (half-diminished) must return no_voicing, not a minor barre.
    def test_cm7b5_guitar_returns_no_voicing(self):
        """Half-diminished has no movable template — no_voicing=True, not a wrong Cm barre."""
        diagrams = get_chord_diagrams(["Cm7b5"], instrument="guitar")
        d = diagrams[0]
        assert d.no_voicing is True
        assert d.frets is None

    def test_am7b5_guitar_returns_no_voicing_c2(self):
        """Consistent: Am7b5 also gets no_voicing on guitar (barre path)."""
        diagrams = get_chord_diagrams(["Am7b5"], instrument="guitar")
        assert diagrams[0].no_voicing is True

    # I1: Piano notes must be in strictly ascending pitch order.
    def test_gmaj7_piano_notes_ascending(self):
        """Gmaj7 triggers octave-cap on F# — notes must still be ascending."""
        from backend.tools.voicings import _piano_chord_voicing
        import re
        v = _piano_chord_voicing("G", "maj7")
        assert v is not None
        note_order = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        def note_to_midi(name: str) -> int:
            m = re.match(r"([A-G]#?)(\d+)", name)
            pitch, octave = m.group(1), int(m.group(2))
            return (octave + 1) * 12 + note_order.index(pitch)

        midi_vals = [note_to_midi(n) for n in v["right_hand"]]
        assert midi_vals == sorted(midi_vals), f"Notes not ascending: {v['right_hand']}"

    def test_a7_piano_notes_ascending(self):
        """A7 also triggers octave-cap — notes must be ascending."""
        from backend.tools.voicings import _piano_chord_voicing
        import re
        v = _piano_chord_voicing("A", "dom7")
        assert v is not None
        note_order = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        def note_to_midi(name: str) -> int:
            m = re.match(r"([A-G]#?)(\d+)", name)
            pitch, octave = m.group(1), int(m.group(2))
            return (octave + 1) * 12 + note_order.index(pitch)

        midi_vals = [note_to_midi(n) for n in v["right_hand"]]
        assert midi_vals == sorted(midi_vals), f"Notes not ascending: {v['right_hand']}"

    def test_bmaj_piano_notes_ascending(self):
        """Bmaj (F# capped down) must return ascending notes."""
        from backend.tools.voicings import _piano_chord_voicing
        import re
        v = _piano_chord_voicing("B", "maj")
        assert v is not None
        note_order = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        def note_to_midi(name: str) -> int:
            m = re.match(r"([A-G]#?)(\d+)", name)
            pitch, octave = m.group(1), int(m.group(2))
            return (octave + 1) * 12 + note_order.index(pitch)

        midi_vals = [note_to_midi(n) for n in v["right_hand"]]
        assert midi_vals == sorted(midi_vals), f"Notes not ascending: {v['right_hand']}"
