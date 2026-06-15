"""Phase 5 G2 — deterministic downbeat + time-signature detection.

Pure numpy: ``detect_meter`` is fed a beat-synchronous accent array (the
relative strength of each beat) and recovers the measure length, the
downbeat phase, and a confidence — no audio, no librosa, no ml marker, so
these run in the default CI selection.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.ml.meter import (
    MIN_BEATS_FOR_METER,
    TIME_SIGNATURES,
    MeterResult,
    beat_accents,
    detect_meter,
)


def _accent_grid(n_measures: int, numerator: int, offset: int = 0, strong=1.0, weak=0.2):
    """Accent array with a strong beat every `numerator` beats at `offset`."""
    n = n_measures * numerator
    a = np.full(n, weak)
    for i in range(n):
        if (i - offset) % numerator == 0:
            a[i] = strong
    return a


class TestDetectMeterCommonSignatures:
    @pytest.mark.parametrize(
        "numerator,sig",
        [(2, "2/4"), (3, "3/4"), (4, "4/4"), (6, "6/8")],
    )
    def test_recovers_meter_from_clean_accents(self, numerator: int, sig: str):
        accents = _accent_grid(6, numerator)
        result = detect_meter(accents)
        assert result.numerator == numerator
        assert result.offset == 0
        assert result.time_signature == sig
        assert result.confidence > 0.5

    def test_recovers_downbeat_phase(self):
        # Strong beat on the 2nd beat (offset 1) in 4/4.
        accents = _accent_grid(6, 4, offset=1)
        result = detect_meter(accents)
        assert result.numerator == 4
        assert result.offset == 1

    def test_three_four_not_confused_with_six_eight(self):
        # True 3/4: strong every 3 (so beats 0,3,6,9 strong) must read as 3, not 6.
        result = detect_meter(_accent_grid(8, 3))
        assert result.numerator == 3

    def test_six_eight_single_primary_accent(self):
        # One primary accent per 6 reads as 6/8, not 3/4.
        result = detect_meter(_accent_grid(6, 6))
        assert result.numerator == 6
        assert result.time_signature == "6/8"


class TestDetectMeterDegenerate:
    def test_flat_accents_default_to_four_four_low_confidence(self):
        result = detect_meter(np.full(48, 0.5))
        assert result.numerator == 4
        assert result.offset == 0
        assert result.time_signature == "4/4"
        assert result.confidence == 0.0

    def test_too_few_beats_default(self):
        result = detect_meter(np.array([1.0, 0.2, 0.2]))
        assert result.numerator == 4
        assert result.confidence == 0.0
        assert MIN_BEATS_FOR_METER >= 8

    def test_noise_low_confidence(self):
        rng = np.random.default_rng(11)
        confs = [detect_meter(rng.random(48)).confidence for _ in range(40)]
        assert float(np.mean(confs)) < 0.4

    def test_empty_input(self):
        result = detect_meter(np.array([]))
        assert result.numerator == 4 and result.confidence == 0.0


class TestDetectMeterContracts:
    def test_confidence_in_unit_range(self):
        for num in (2, 3, 4, 6):
            c = detect_meter(_accent_grid(6, num)).confidence
            assert 0.0 <= c <= 1.0

    def test_scale_invariant(self):
        a = _accent_grid(6, 3)
        assert detect_meter(a) == detect_meter(a * 100.0)

    def test_deterministic(self):
        a = _accent_grid(6, 4, offset=2)
        assert detect_meter(a) == detect_meter(a)

    def test_result_is_frozen_dataclass(self):
        from dataclasses import FrozenInstanceError

        r = MeterResult(numerator=4, offset=0, time_signature="4/4", confidence=0.9)
        with pytest.raises(FrozenInstanceError):
            r.numerator = 3  # frozen

    def test_time_signatures_map_covers_candidates(self):
        for num in (2, 3, 4, 6):
            assert num in TIME_SIGNATURES


class TestBeatAccents:
    def test_samples_onset_strength_at_beats(self):
        # Onset envelope with peaks at frames 10, 20, 30; beats at those frames.
        onset = np.zeros(40)
        onset[[10, 20, 30]] = [1.0, 0.3, 0.9]
        beats = np.array([10, 20, 30])
        acc = beat_accents(onset, beats)
        assert acc.shape == (3,)
        # Peak-in-window picks up the onset value at/after each beat frame.
        assert acc[0] > acc[1] and acc[2] > acc[1]

    def test_handles_beats_near_end(self):
        onset = np.zeros(15)
        onset[14] = 1.0
        acc = beat_accents(onset, np.array([14]))
        assert acc.shape == (1,)
        assert acc[0] == pytest.approx(1.0)

    def test_empty_beats(self):
        assert beat_accents(np.zeros(10), np.array([])).shape == (0,)
