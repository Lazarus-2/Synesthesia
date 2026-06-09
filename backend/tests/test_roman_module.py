"""G1.2–G1.11: backend.theory.roman module tests."""


def test_module_importable():
    from backend.theory import roman  # noqa: F401


def test_to_m21_converts_flat_root():
    from backend.theory.roman import _to_m21
    assert _to_m21("Bb") == "B-"
    assert _to_m21("Eb7") == "E-7"
    assert _to_m21("Ab") == "A-"
    assert _to_m21("Db") == "D-"
    assert _to_m21("Gb") == "G-"


def test_to_m21_leaves_sharps_and_naturals_alone():
    from backend.theory.roman import _to_m21
    assert _to_m21("F#m7") == "F#m7"
    assert _to_m21("Cmaj7") == "Cmaj7"
    assert _to_m21("G") == "G"


def test_to_m21_converts_slash_bass_flat():
    from backend.theory.roman import _to_m21
    # Both root and bass need conversion
    assert _to_m21("Bb/D") == "B-/D"
    assert _to_m21("G/Bb") == "G/B-"
    assert _to_m21("Eb/Bb") == "E-/B-"


def test_to_m21_handles_no_chord_markers():
    from backend.theory.roman import _to_m21
    assert _to_m21("N.C.") == "N.C."
    assert _to_m21("") == ""


# ---------------------------------------------------------------------------
# G1.3 — smart_analyze
# ---------------------------------------------------------------------------

def test_smart_analyze_diatonic_triads_c_major():
    from backend.theory.roman import smart_analyze
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    cases = [
        ("C",    "I"),
        ("Dm",   "ii"),
        ("Em",   "iii"),
        ("F",    "IV"),
        ("G",    "V"),
        ("Am",   "vi"),
        ("Bdim", "viio"),
    ]
    for sym, expected_fig in cases:
        rn = smart_analyze(sym, k)
        assert rn.figure == expected_fig, (
            f"smart_analyze({sym!r}, C major) = {rn.figure!r}, expected {expected_fig!r}"
        )


def test_smart_analyze_seventh_chords():
    from backend.theory.roman import smart_analyze
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    assert smart_analyze("G7", k).figure == "V7"
    assert smart_analyze("Fmaj7", k).figure == "IV7"
    assert smart_analyze("Am7", k).figure == "vi7"


def test_smart_analyze_inversions():
    from backend.theory.roman import smart_analyze
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    rn_c_e = smart_analyze("C/E", k)
    assert rn_c_e.figure == "I6"
    assert rn_c_e.inversion() == 1

    rn_g_b = smart_analyze("G/B", k)
    assert rn_g_b.figure == "V6"
    assert rn_g_b.inversion() == 1


def test_smart_analyze_no_chord_returns_none():
    from backend.theory.roman import smart_analyze
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    assert smart_analyze("N.C.", k) is None
    assert smart_analyze("", k) is None


# ---------------------------------------------------------------------------
# G1.4 — is_secondary / is_borrowed
# ---------------------------------------------------------------------------

def test_secondary_dominant_d7_in_c():
    from backend.theory.roman import smart_analyze, is_secondary, is_borrowed
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    rn = smart_analyze("D7", k)
    assert rn.figure == "V7/V"
    assert is_secondary(rn) is True
    assert is_borrowed(rn) is False


def test_secondary_dominant_a7_in_c():
    from backend.theory.roman import smart_analyze, is_secondary, is_borrowed
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    rn = smart_analyze("A7", k)
    assert rn.figure == "V7/ii"
    assert is_secondary(rn) is True
    assert is_borrowed(rn) is False


def test_secondary_dominant_e7_in_c():
    from backend.theory.roman import smart_analyze, is_secondary
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    rn = smart_analyze("E7", k)
    assert rn.figure == "V7/vi"
    assert is_secondary(rn) is True


def test_borrowed_chord_bb_in_c():
    from backend.theory.roman import smart_analyze, is_secondary, is_borrowed
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    rn = smart_analyze("Bb", k)
    assert rn.figure == "bVII"
    assert is_borrowed(rn) is True
    assert is_secondary(rn) is False


def test_borrowed_chord_ab_in_c():
    from backend.theory.roman import smart_analyze, is_borrowed
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    rn = smart_analyze("Ab", k)
    assert is_borrowed(rn) is True


def test_diatonic_chords_not_borrowed_not_secondary():
    from backend.theory.roman import smart_analyze, is_secondary, is_borrowed
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    for sym in ("C", "Am", "G", "G7", "F", "Fmaj7", "C/E"):
        rn = smart_analyze(sym, k)
        assert not is_secondary(rn), f"{sym} wrongly flagged as secondary"
        assert not is_borrowed(rn), f"{sym} wrongly flagged as borrowed"


# ---------------------------------------------------------------------------
# G1.5 — harmonic_function
# ---------------------------------------------------------------------------

def test_function_classifier_major():
    from backend.theory.roman import smart_analyze, harmonic_function
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    cases = [
        ("C",    "tonic"),
        ("Am",   "submediant"),
        ("G",    "dominant"),
        ("G7",   "dominant"),
        ("F",    "subdominant"),
        ("Fmaj7","subdominant"),
        ("Dm",   "supertonic"),
        ("Em",   "mediant"),
        ("Bdim", "leading_tone"),
        ("D7",   "secondary_dominant"),
        ("Bb",   "chromatic"),       # borrowed -> chromatic function
    ]
    for sym, expected_func in cases:
        rn = smart_analyze(sym, k)
        result = harmonic_function(rn)
        assert result == expected_func, (
            f"harmonic_function({sym!r}) = {result!r}, expected {expected_func!r}"
        )


def test_function_classifier_minor():
    from backend.theory.roman import smart_analyze, harmonic_function
    from music21 import key as m21key
    k = m21key.Key("a", "minor")
    cases = [
        ("Am",   "tonic"),
        ("E",    "dominant"),
        ("E7",   "dominant"),   # V7 in minor is diatonic with raised leading tone
        ("Dm",   "subdominant"),
        # Adaptation: F in Am = bVI (submediant), not bIII (mediant).
        # music21 returns bVI for F in A minor (6th degree of natural minor scale).
        ("F",    "submediant"),
    ]
    for sym, expected_func in cases:
        rn = smart_analyze(sym, k)
        result = harmonic_function(rn)
        assert result == expected_func, (
            f"harmonic_function({sym!r}, a minor) = {result!r}, expected {expected_func!r}"
        )


# ---------------------------------------------------------------------------
# G1.6 — detect_cadence
# ---------------------------------------------------------------------------

def test_cadence_pac():
    from backend.theory.roman import smart_analyze, detect_cadence
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    # Perfect authentic: V -> I, both root position
    assert detect_cadence(smart_analyze("G", k), smart_analyze("C", k)) == "PAC"
    assert detect_cadence(smart_analyze("G7", k), smart_analyze("C", k)) == "PAC"


def test_cadence_iac():
    from backend.theory.roman import smart_analyze, detect_cadence
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    # Imperfect authentic: V -> I but I is inverted OR V is inverted
    assert detect_cadence(smart_analyze("G/B", k), smart_analyze("C", k)) == "IAC"


def test_cadence_deceptive():
    from backend.theory.roman import smart_analyze, detect_cadence
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    # Deceptive: V -> vi
    assert detect_cadence(smart_analyze("G7", k), smart_analyze("Am", k)) == "deceptive"
    assert detect_cadence(smart_analyze("G", k), smart_analyze("Am", k)) == "deceptive"


def test_cadence_half():
    from backend.theory.roman import smart_analyze, detect_cadence
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    # Half cadence: any -> V (root position)
    assert detect_cadence(smart_analyze("F", k), smart_analyze("G", k)) == "half"
    assert detect_cadence(smart_analyze("Dm", k), smart_analyze("G", k)) == "half"


def test_cadence_plagal():
    from backend.theory.roman import smart_analyze, detect_cadence
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    # Plagal: IV -> I
    assert detect_cadence(smart_analyze("F", k), smart_analyze("C", k)) == "plagal"


def test_cadence_none_for_non_cadential():
    from backend.theory.roman import smart_analyze, detect_cadence
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    # I -> IV, I -> ii, etc. are not cadences
    assert detect_cadence(smart_analyze("C", k), smart_analyze("F", k)) is None
    assert detect_cadence(smart_analyze("C", k), smart_analyze("Am", k)) is None


# ---------------------------------------------------------------------------
# G1.7 — RomanEntry schema + enriched RomanAnalysis
# ---------------------------------------------------------------------------

def test_roman_entry_schema():
    from backend.schemas import RomanEntry
    entry = RomanEntry(
        chord="G7",
        numeral="V7",
        function="dominant",
        inversion=0,
        is_secondary=False,
        is_borrowed=False,
        cadence=None,
        start=2.0,
        end=4.0,
    )
    assert entry.numeral == "V7"
    assert entry.start == 2.0


def test_roman_analysis_has_entries_cadences_modulations():
    from backend.schemas import RomanAnalysis, RomanEntry
    ra = RomanAnalysis(
        key="C major",
        progression=["I", "V7", "vi"],
        function=["tonic", "dominant", "submediant"],
        entries=[
            RomanEntry(chord="C", numeral="I", function="tonic",
                       inversion=0, is_secondary=False, is_borrowed=False,
                       cadence=None, start=0.0, end=2.0),
        ],
        cadences=[{"type": "PAC", "index": 1}],
        modulations=[],
    )
    assert len(ra.entries) == 1
    assert ra.cadences[0]["type"] == "PAC"
    assert ra.modulations == []


def test_roman_analysis_summary_progression_optional():
    from backend.schemas import RomanAnalysis
    ra = RomanAnalysis(
        key="C major",
        progression=["I", "V", "vi", "IV"],
        function=["tonic", "dominant", "submediant", "subdominant"],
    )
    # summary_progression defaults to None when omitted
    assert ra.summary_progression is None


# ---------------------------------------------------------------------------
# G1.8 — detect_modulations
# ---------------------------------------------------------------------------

def test_detect_modulations_no_modulation():
    from backend.theory.roman import detect_modulations
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    # Classic I-V-vi-IV loop — no modulation
    symbols = ["C", "G", "Am", "F", "C", "G", "Am", "F"]
    mods = detect_modulations(symbols, k)
    assert mods == []


def test_detect_modulations_finds_relative_shift():
    from backend.theory.roman import detect_modulations
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    # First 4 chords in C, then sustained shift to a different tonal centre.
    # D A Bm G is I-V-vi-IV in D major, so music21 correctly detects D major.
    # (Adaptation from plan: the plan said "G major" but the chord sequence
    # D-A-Bm-G is the D major I-V-vi-IV loop, not G major's.)
    symbols = ["C", "G", "Am", "F", "D", "A", "Bm", "G", "D", "A", "Bm", "G"]
    mods = detect_modulations(symbols, k)
    # Should detect at least one modulation away from C major
    assert len(mods) >= 1
    assert all(m["to_key"] != "C major" for m in mods)


def test_detect_modulations_returns_at_index():
    from backend.theory.roman import detect_modulations
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    symbols = ["C", "G", "Am", "F", "D", "A", "Bm", "G", "D", "A", "Bm", "G"]
    mods = detect_modulations(symbols, k)
    for m in mods:
        assert "to_key" in m
        assert "at_index" in m
        assert isinstance(m["at_index"], int)


# ---------------------------------------------------------------------------
# G1.9 — analyze_roman public API
# ---------------------------------------------------------------------------

def test_analyze_roman_returns_roman_analysis():
    from backend.theory.roman import analyze_roman
    from backend.schemas import RomanAnalysis, ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="G7"),
        ChordEvent(start=4.0, end=6.0, chord="Am"),
        ChordEvent(start=6.0, end=8.0, chord="F"),
    ]
    result = analyze_roman(chords, "C major")

    assert isinstance(result, RomanAnalysis)
    assert result.key == "C major"
    assert len(result.entries) == 4
    assert result.entries[0].numeral == "I"
    assert result.entries[1].numeral == "V7"
    assert result.entries[2].numeral == "vi"
    assert result.entries[3].numeral == "IV"


def test_analyze_roman_entries_are_time_aligned():
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=1.5, chord="C"),
        ChordEvent(start=1.5, end=3.0, chord="G"),
    ]
    result = analyze_roman(chords, "C major")
    assert result.entries[0].start == 0.0
    assert result.entries[0].end == 1.5
    assert result.entries[1].start == 1.5
    assert result.entries[1].end == 3.0


def test_analyze_roman_populates_legacy_fields():
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="G7"),
        ChordEvent(start=4.0, end=6.0, chord="Am"),
        ChordEvent(start=6.0, end=8.0, chord="F"),
    ]
    result = analyze_roman(chords, "C major")
    # Legacy fields must be populated (back-compat for TheoryPanel.tsx)
    assert result.progression == ["I", "V7", "vi", "IV"]
    assert result.function == ["tonic", "dominant", "submediant", "subdominant"]
    # summary_progression capped at <=8
    assert result.summary_progression is not None
    assert len(result.summary_progression) <= 8


def test_analyze_roman_cadences_pac_detected():
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="F"),
        ChordEvent(start=2.0, end=4.0, chord="G"),
        ChordEvent(start=4.0, end=6.0, chord="C"),
    ]
    result = analyze_roman(chords, "C major")
    # G -> C = PAC
    cadence_types = [c["type"] for c in result.cadences]
    assert "PAC" in cadence_types


def test_analyze_roman_secondary_dominant_flagged():
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="D7"),
        ChordEvent(start=4.0, end=6.0, chord="G"),
    ]
    result = analyze_roman(chords, "C major")
    d7_entry = next(e for e in result.entries if e.chord == "D7")
    assert d7_entry.numeral == "V7/V"
    assert d7_entry.is_secondary is True


def test_analyze_roman_borrowed_chord_flagged():
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="Bb"),
        ChordEvent(start=4.0, end=6.0, chord="F"),
        ChordEvent(start=6.0, end=8.0, chord="C"),
    ]
    result = analyze_roman(chords, "C major")
    bb_entry = next(e for e in result.entries if e.chord == "Bb")
    assert bb_entry.is_borrowed is True
    assert bb_entry.numeral == "bVII"


def test_analyze_roman_no_chord_tokens_skipped():
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="N.C."),
        ChordEvent(start=4.0, end=6.0, chord="G"),
    ]
    result = analyze_roman(chords, "C major")
    # N.C. is skipped — only 2 entries
    assert len(result.entries) == 2


# ---------------------------------------------------------------------------
# G1.10 — No-music21 fallback
# ---------------------------------------------------------------------------

def test_fallback_when_music21_unavailable(monkeypatch):
    """analyze_roman must not raise when music21 is import-guarded out."""
    import backend.theory.roman as roman_mod
    monkeypatch.setattr(roman_mod, "_MUSIC21_AVAILABLE", False)

    from backend.schemas import ChordEvent, RomanAnalysis
    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="G"),
        ChordEvent(start=4.0, end=6.0, chord="Am"),
        ChordEvent(start=6.0, end=8.0, chord="F"),
    ]
    result = roman_mod.analyze_roman(chords, "C major")
    assert isinstance(result, RomanAnalysis)
    # Fallback still populates progression and function (legacy shape)
    assert len(result.progression) > 0
    assert len(result.function) > 0
    # entries and enriched fields may be empty in fallback
    # but must not raise


def test_fallback_produces_basic_diatonic_numerals(monkeypatch):
    import backend.theory.roman as roman_mod
    monkeypatch.setattr(roman_mod, "_MUSIC21_AVAILABLE", False)

    from backend.schemas import ChordEvent
    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="G"),
    ]
    result = roman_mod.analyze_roman(chords, "C major")
    assert "I" in result.progression
    assert "V" in result.progression


# ---------------------------------------------------------------------------
# G1-review fixes
# ---------------------------------------------------------------------------

# C1 — garbage chord does NOT abort the whole analysis
def test_garbage_chord_skipped_keeps_good_chords():
    """A single unparseable symbol ('Bbb', whitespace) is skipped; good chords survive."""
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="Bbb"),   # invalid -> skipped
        ChordEvent(start=4.0, end=6.0, chord="   "),   # whitespace-only -> skipped
        ChordEvent(start=6.0, end=8.0, chord="G"),
    ]
    result = analyze_roman(chords, "C major")
    # Only C and G should appear
    assert len(result.entries) == 2
    assert result.entries[0].chord == "C"
    assert result.entries[1].chord == "G"


def test_whitespace_chord_skipped():
    """smart_analyze returns None for whitespace-only chord symbols."""
    from backend.theory.roman import smart_analyze
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    assert smart_analyze("   ", k) is None
    assert smart_analyze("\t", k) is None


# I1 — bVII/bVI/bIII in minor NOT relabelled as secondary dominants
def test_bvii_in_minor_not_secondary():
    """G in A minor should be bVII, not V/III."""
    from backend.theory.roman import smart_analyze, is_secondary
    from music21 import key as m21key
    k = m21key.Key("a", "minor")
    rn = smart_analyze("G", k)
    assert rn is not None
    assert rn.figure == "bVII", f"Expected bVII, got {rn.figure!r}"
    assert is_secondary(rn) is False


def test_bvi_in_minor_not_secondary():
    """F in A minor should be bVI, not a secondary dominant."""
    from backend.theory.roman import smart_analyze, is_secondary
    from music21 import key as m21key
    k = m21key.Key("a", "minor")
    rn = smart_analyze("F", k)
    assert rn is not None
    assert rn.figure == "bVI", f"Expected bVI, got {rn.figure!r}"
    assert is_secondary(rn) is False


def test_am_f_g_am_labels_bvii():
    """Am-F-G-Am progression: G is labelled bVII in A minor context."""
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="Am"),
        ChordEvent(start=2.0, end=4.0, chord="F"),
        ChordEvent(start=4.0, end=6.0, chord="G"),
        ChordEvent(start=6.0, end=8.0, chord="Am"),
    ]
    result = analyze_roman(chords, "A minor")
    g_entry = next(e for e in result.entries if e.chord == "G")
    assert g_entry.numeral == "bVII", f"Expected bVII, got {g_entry.numeral!r}"
    assert g_entry.is_secondary is False


# I2 — cadence pass reuses retained RN objects (observable via correctness)
def test_cadence_still_detected_after_i2_refactor():
    """PAC cadence is still detected correctly after the I2 rn_objects refactor."""
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="F"),
        ChordEvent(start=2.0, end=4.0, chord="G"),
        ChordEvent(start=4.0, end=6.0, chord="C"),
    ]
    result = analyze_roman(chords, "C major")
    cadence_types = [c["type"] for c in result.cadences]
    assert "PAC" in cadence_types


# I3 — detect_modulations capped at max_modulations
def test_detect_modulations_capped():
    """A noisy/random-ish long progression yields ≤ 8 modulations."""
    from backend.theory.roman import detect_modulations
    from music21 import key as m21key
    import random
    random.seed(0)
    key_c = m21key.Key("C", "major")
    all_chords = ["C", "G", "Am", "F", "D", "A", "Bm", "E", "B", "F#m",
                  "Ab", "Eb", "Bb", "Dm", "Em", "Cm", "Gm"]
    long_prog = [random.choice(all_chords) for _ in range(60)]
    mods = detect_modulations(long_prog, key_c)
    assert len(mods) <= 8, f"Expected ≤ 8 modulations, got {len(mods)}: {mods}"


def test_detect_modulations_genuine_modulation_still_found():
    """A genuine modulation (C → D major) is still detected even with the cap."""
    from backend.theory.roman import detect_modulations
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    # First 4 chords in C; then a sustained D-major run
    symbols = ["C", "G", "Am", "F", "D", "A", "Bm", "G", "D", "A", "Bm", "G"]
    mods = detect_modulations(symbols, k)
    assert len(mods) >= 1
    assert all(m["to_key"] != "C major" for m in mods)


# Modal mixture (should-fix): Fm in C major
def test_fm_in_c_major_is_borrowed():
    """Fm in C major should be is_borrowed=True, function='chromatic'."""
    from backend.theory.roman import smart_analyze, is_borrowed, harmonic_function
    from music21 import key as m21key
    k = m21key.Key("C", "major")
    rn = smart_analyze("Fm", k)
    assert rn is not None
    assert is_borrowed(rn) is True, f"Fm in C major should be borrowed; figure={rn.figure!r}"
    assert harmonic_function(rn) == "chromatic", (
        f"Fm in C major should have function 'chromatic'; got {harmonic_function(rn)!r}"
    )


def test_fm_in_c_major_flagged_in_analyze_roman():
    """analyze_roman flags Fm (iv) in C major as is_borrowed=True."""
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="C"),
        ChordEvent(start=2.0, end=4.0, chord="Fm"),
        ChordEvent(start=4.0, end=6.0, chord="C"),
    ]
    result = analyze_roman(chords, "C major")
    fm_entry = next(e for e in result.entries if e.chord == "Fm")
    assert fm_entry.is_borrowed is True
    assert fm_entry.function == "chromatic"


# E7 in minor figure normalisation (should-fix)
def test_e7_in_minor_normalized():
    """E7 in A minor should produce numeral 'V7', not 'V75#3'."""
    from backend.theory.roman import analyze_roman
    from backend.schemas import ChordEvent

    chords = [
        ChordEvent(start=0.0, end=2.0, chord="Am"),
        ChordEvent(start=2.0, end=4.0, chord="E7"),
        ChordEvent(start=4.0, end=6.0, chord="Am"),
    ]
    result = analyze_roman(chords, "A minor")
    e7_entry = next(e for e in result.entries if e.chord == "E7")
    assert e7_entry.numeral == "V7", (
        f"E7 in A minor: expected numeral 'V7', got {e7_entry.numeral!r}"
    )
    assert e7_entry.function == "dominant"


# Legacy fallback enharmonics (should-fix)
def test_legacy_fallback_enharmonics_cb_fb(monkeypatch):
    """CB (C-flat = B) and FB (F-flat = E) are recognized in the legacy fallback."""
    import backend.theory.roman as roman_mod
    monkeypatch.setattr(roman_mod, "_MUSIC21_AVAILABLE", False)

    from backend.schemas import ChordEvent
    chords = [
        ChordEvent(start=0.0, end=2.0, chord="Cb"),   # Cb = B -> leading_tone in C major
        ChordEvent(start=2.0, end=4.0, chord="Fb"),   # Fb = E -> mediant in C major
    ]
    result = roman_mod.analyze_roman(chords, "C major")
    # Cb = B pitch class 11 -> vii° in C major diatonic map -> not '?'
    assert result.progression[0] != "?", f"Cb should map to a diatonic numeral, got {result.progression[0]!r}"
    # Fb = E pitch class 4 -> iii in C major diatonic map -> not '?'
    assert result.progression[1] != "?", f"Fb should map to a diatonic numeral, got {result.progression[1]!r}"
