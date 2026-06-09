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
