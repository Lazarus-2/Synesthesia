"""G1.2: backend.theory.roman module exists with _to_m21 helper."""
import pytest


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
