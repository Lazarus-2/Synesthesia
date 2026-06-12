"""Phase 4 G3 — consumer fixes so the 84-chord vocabulary survives downstream.

Covers the probe-verified bugs from docs/audit/PHASE4_PREFLIGHT_AUDIT.md:
- VOICE-SUS: Caug/Csus2/Csus4 returned the C-major open shape on guitar/uke.
- ROMAN-SUS: Csus4 in C major labeled ``i54``/chromatic/borrowed.
- ROMAN-FIG: ``F7``→``IVb753``, ``Bdim7``→``viiob753`` figured-bass garbage.
- ROMAN-BLUES: blues tonic ``C7`` in C labeled ``V7/IV`` secondary.
- COLOR-EXT: ``Cm11``/``Cm13`` colored as pure major red; sus = plain major.
"""

from __future__ import annotations

import pytest

from backend.tools.synesthesia_colors import get_chord_color
from backend.tools.voicings import get_chord_diagrams

# Guitar standard tuning EADGBe / ukulele GCEA as pitch classes.
_GUITAR_OPEN_PCS = [4, 9, 2, 7, 11, 4]
_UKE_OPEN_PCS = [7, 0, 4, 9]

_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_QUALITY_PCS = {
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "aug": (0, 4, 8),
}


def _sounded_pcs(frets: list[int], open_pcs: list[int]) -> set[int]:
    return {(o + f) % 12 for o, f in zip(open_pcs, frets) if f >= 0}


class TestSusAugVoicings:
    """A diagram must contain exactly the chord's tones — or honestly say no_voicing."""

    @pytest.mark.parametrize("root", range(12))
    @pytest.mark.parametrize("suffix", ["sus2", "sus4", "aug"])
    def test_guitar_shape_is_correct_or_absent(self, root: int, suffix: str):
        label = f"{_NOTES[root]}{suffix}"
        [d] = get_chord_diagrams([label], instrument="guitar")
        if d.no_voicing:
            return  # honest absence beats a wrong shape
        expected = {(root + iv) % 12 for iv in _QUALITY_PCS[suffix]}
        assert _sounded_pcs(d.frets, _GUITAR_OPEN_PCS) == expected, label

    def test_csus4_guitar_is_not_the_c_major_open_shape(self):
        [d] = get_chord_diagrams(["Csus4"], instrument="guitar")
        assert d.no_voicing or d.frets != [-1, 3, 2, 0, 1, 0]

    def test_sus4_has_a_real_guitar_shape_for_every_root(self):
        # sus4 has both E- and A-form movable templates, so no root should
        # need the no_voicing escape hatch.
        for root in _NOTES:
            [d] = get_chord_diagrams([f"{root}sus4"], instrument="guitar")
            assert not d.no_voicing, f"{root}sus4 lost its shape"

    @pytest.mark.parametrize("suffix", ["sus2", "sus4", "aug"])
    def test_ukulele_never_shows_the_major_shape(self, suffix: str):
        [d] = get_chord_diagrams([f"C{suffix}"], instrument="ukulele")
        if not d.no_voicing:
            expected = {(0 + iv) % 12 for iv in _QUALITY_PCS[suffix]}
            assert _sounded_pcs(d.frets, _UKE_OPEN_PCS) == expected

    def test_minor_family_fallback_untouched(self):
        [d] = get_chord_diagrams(["Am9"], instrument="guitar")
        assert not d.no_voicing  # still degrades to the Am family shape


class TestRomanSusHandling:
    def _analyze(self, chords: list[str], key: str):
        from backend.theory.roman import analyze_roman

        events = [
            {"chord": c, "start": float(i), "end": float(i + 1)}
            for i, c in enumerate(chords)
        ]
        return analyze_roman(events, key)

    def test_tonic_sus4_in_major(self):
        result = self._analyze(["Csus4", "C"], "C major")
        entry = result.entries[0]
        assert entry.numeral == "Isus4"
        assert entry.function == "tonic"
        assert entry.is_borrowed is False
        assert entry.is_secondary is False

    def test_dominant_sus4_in_major(self):
        result = self._analyze(["Gsus4", "G", "C"], "C major")
        entry = result.entries[0]
        assert entry.numeral == "Vsus4"
        assert entry.function == "dominant"
        assert entry.is_borrowed is False

    def test_sus2_in_minor(self):
        result = self._analyze(["Asus2"], "A minor")
        entry = result.entries[0]
        assert entry.numeral == "Isus2"
        assert entry.function == "tonic"
        assert entry.is_borrowed is False


class TestRomanFigureCleanup:
    def _entries(self, chords: list[str], key: str):
        from backend.theory.roman import analyze_roman

        events = [
            {"chord": c, "start": float(i), "end": float(i + 1)}
            for i, c in enumerate(chords)
        ]
        return analyze_roman(events, key).entries

    def test_subdominant_seventh_figure_is_clean(self):
        [entry] = self._entries(["F7"], "C major")
        assert entry.numeral == "IV7"
        assert entry.is_secondary is False

    def test_diminished_seventh_figure_is_clean(self):
        [entry] = self._entries(["Bdim7"], "C major")
        assert entry.numeral == "viio7"

    def test_inversion_figures_are_preserved(self):
        [entry] = self._entries(["C/E"], "C major")
        assert entry.numeral == "I6"  # first inversion must NOT be flattened

    def test_harmonic_minor_v7_still_simplified(self):
        entries = self._entries(["E7", "Am"], "A minor")
        assert entries[0].numeral == "V7"


class TestRomanBluesGuard:
    def _entries(self, chords: list[str], key: str):
        from backend.theory.roman import analyze_roman

        events = [
            {"chord": c, "start": float(i), "end": float(i + 1)}
            for i, c in enumerate(chords)
        ]
        return analyze_roman(events, key).entries

    def test_blues_tonic_dom7_is_I7_not_secondary(self):
        [entry] = self._entries(["C7"], "C major")
        assert entry.numeral == "I7"
        assert entry.is_secondary is False
        assert entry.function != "secondary_dominant"

    def test_blues_subdominant_dom7_is_IV7(self):
        entries = self._entries(["C7", "F7", "G7", "C7"], "C major")
        assert entries[1].numeral == "IV7"
        assert entries[1].is_secondary is False

    def test_genuine_secondary_dominants_survive(self):
        # D7 in C major is V7/V — the guard must not flatten real secondaries.
        [entry] = self._entries(["D7"], "C major")
        assert entry.is_secondary is True
        assert "/" in entry.numeral

    def test_plain_dominant_seventh_unaffected(self):
        entries = self._entries(["G7", "C"], "C major")
        assert entries[0].numeral == "V7"
        assert entries[0].function == "dominant"


class TestColorExtensions:
    def test_minor_extensions_use_the_minor_branch(self):
        minor_color = get_chord_color("Cm")
        assert get_chord_color("Cm11") == minor_color
        assert get_chord_color("Cm13") == minor_color
        assert get_chord_color("Cm11") != "#FF0000"

    def test_sus_chords_are_not_plain_major(self):
        major = get_chord_color("C")
        assert get_chord_color("Csus4") != major
        assert get_chord_color("Csus2") != major

    def test_sus_color_keeps_the_root_hue_family(self):
        # Same root => same base hue; sus only changes saturation/lightness,
        # so the color must differ from major yet not be a fixed accent swap.
        assert get_chord_color("Csus4") != get_chord_color("Gsus4")

    def test_existing_accents_unchanged(self):
        assert get_chord_color("Bdim") == "#FF00C8"
        assert get_chord_color("Caug") == "#B6FF00"
        assert get_chord_color("N.C.") == "#1A1A1A"
