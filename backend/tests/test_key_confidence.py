"""Phase 4 G4 — key/tempo confidence (ML-03). Pure numpy, CI-visible.

Covers: KeyTempoResult dataclass, calibrated Krumhansl-Schmuckler confidence
(NaN/silent fallbacks => 0.0), relative-key disambiguation via tonic evidence,
and the unified tempo source (median beat interval + octave fold + confidence
from beat-interval consistency).
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.ml.key_estimation import (
    MIN_BEATS_FOR_TEMPO,
    TEMPO_FOLD_RANGE,
    KeyTempoResult,
    _krumhansl_schmuckler,
    disambiguate_relative_key,
    refine_tempo,
)

_KS_MAJOR = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)


class TestKeyConfidence:
    def test_clean_profile_high_confidence(self):
        key, conf = _krumhansl_schmuckler(_KS_MAJOR.copy())
        assert key == "C major"
        assert conf > 0.7

    def test_diatonic_mix_confident(self):
        chroma = np.array([1.0, 0, 0.5, 0, 0.6, 0.55, 0, 0.8, 0, 0.5, 0, 0.3])
        key, conf = _krumhansl_schmuckler(chroma)
        assert key == "C major"
        assert conf > 0.6

    def test_bare_triad_moderately_confident(self):
        chroma = np.zeros(12)
        chroma[[0, 4, 7]] = 1.0
        key, conf = _krumhansl_schmuckler(chroma)
        assert key == "C major"
        assert conf > 0.4

    def test_noise_low_confidence(self):
        rng = np.random.default_rng(7)
        confs = [_krumhansl_schmuckler(rng.random(12))[1] for _ in range(50)]
        assert float(np.mean(confs)) < 0.3

    def test_flat_chroma_is_zero_confidence(self):
        # Constant chroma makes corrcoef NaN — must yield the safe fallback.
        key, conf = _krumhansl_schmuckler(np.ones(12))
        assert key == "C major"
        assert conf == 0.0

    def test_confidence_scale_invariant(self):
        chroma = _KS_MAJOR.copy()
        assert _krumhansl_schmuckler(chroma) == _krumhansl_schmuckler(chroma * 37.0)

    def test_result_dataclass_shape(self):
        r = KeyTempoResult(key="C major", key_confidence=0.5, tempo=120.0, tempo_confidence=0.4)
        assert (r.key, r.key_confidence, r.tempo, r.tempo_confidence) == (
            "C major", 0.5, 120.0, 0.4,
        )


class TestRelativeKeyDisambiguation:
    def test_am_progression_flips_c_major_to_a_minor(self):
        chords = ["Am", "F", "C", "G", "Am", "Dm", "E7", "Am"]
        assert disambiguate_relative_key("C major", chords) == "A minor"

    def test_c_major_progression_stays(self):
        chords = ["C", "F", "G", "Am", "C"]
        assert disambiguate_relative_key("C major", chords) == "C major"

    def test_c_heavy_progression_flips_a_minor_to_c_major(self):
        chords = ["C", "Am", "F", "G", "C"]
        assert disambiguate_relative_key("A minor", chords) == "C major"

    def test_empty_or_nc_chords_unchanged(self):
        assert disambiguate_relative_key("C major", []) == "C major"
        assert disambiguate_relative_key("C major", ["N.C.", "N.C."]) == "C major"

    def test_unparseable_key_unchanged(self):
        assert disambiguate_relative_key("nonsense", ["Am"]) == "nonsense"

    def test_flat_key_names_work(self):
        # Eb major's relative is C minor.
        chords = ["Cm", "Ab", "Eb", "G7", "Cm", "Cm"]
        assert disambiguate_relative_key("Eb major", chords) == "C minor"


class TestRefineTempo:
    def test_perfect_grid_yields_tempo_and_high_confidence(self):
        beats = [0.5 * i for i in range(1, 17)]
        tempo, conf = refine_tempo(99.0, 0.4, beats)
        assert tempo == pytest.approx(120.0, abs=0.5)
        assert conf > 0.9

    def test_jitter_lowers_confidence(self):
        rng = np.random.default_rng(3)
        beats = list(np.cumsum(0.5 + rng.normal(0, 0.05, 24)))
        _, conf_jitter = refine_tempo(99.0, 0.4, beats)
        _, conf_clean = refine_tempo(99.0, 0.4, [0.5 * i for i in range(1, 25)])
        assert conf_jitter < conf_clean

    def test_fast_octave_folds_down(self):
        beats = [0.25 * i for i in range(1, 33)]  # 240 BPM grid
        tempo, _ = refine_tempo(99.0, 0.4, beats)
        assert tempo == pytest.approx(120.0, abs=0.5)

    def test_slow_octave_folds_up(self):
        beats = [1.0 * i for i in range(1, 17)]  # 60 BPM grid
        tempo, _ = refine_tempo(99.0, 0.4, beats)
        assert tempo == pytest.approx(120.0, abs=0.5)
        assert TEMPO_FOLD_RANGE[0] <= tempo < TEMPO_FOLD_RANGE[1]

    def test_sparse_beats_keep_fallback(self):
        tempo, conf = refine_tempo(95.0, 0.4, [0.5, 1.0, 1.5])
        assert (tempo, conf) == (95.0, 0.4)
        assert MIN_BEATS_FOR_TEMPO > 3

    def test_no_beats_keep_fallback(self):
        assert refine_tempo(95.0, 0.0, None) == (95.0, 0.0)


class TestFeaturesNodeConfidenceThreading:
    def _run(self, monkeypatch, chords_labels: list[str]):
        from backend.graph import nodes
        from backend.ml.beat_tracking import BeatTrackingResult
        from backend.schemas import BeatEvent, ChordEvent

        result = KeyTempoResult(
            key="C major", key_confidence=0.8, tempo=99.0, tempo_confidence=0.4
        )
        beats = [BeatEvent(time=0.5 * i, beat_number=(i - 1) % 4 + 1) for i in range(1, 17)]
        chords = [
            ChordEvent(start=float(i), end=float(i + 1), chord=c, confidence=0.9, color="#fff")
            for i, c in enumerate(chords_labels)
        ]
        monkeypatch.setattr(
            "backend.ml.key_estimation.estimate_key_and_tempo", lambda _p: result
        )
        monkeypatch.setattr(
            "backend.ml.beat_tracking.track_beats",
            lambda _p: BeatTrackingResult(beats=beats, time_signature="4/4", meter_confidence=0.9),
        )
        monkeypatch.setattr(
            "backend.ml.chord_detection.detect_chords", lambda _p, beats=None: chords
        )
        monkeypatch.setattr("backend.ml.structure_detection.detect_sections", lambda _p: [])
        return nodes.features_node({"audio_path": "song.mp3", "retries": 0})

    def test_confidences_and_unified_tempo_in_state(self, monkeypatch):
        out = self._run(monkeypatch, ["C", "F", "G", "C"])
        assert out["key"] == "C major"
        assert out["key_confidence"] == 0.8
        assert out["tempo"] == pytest.approx(120.0, abs=0.5)  # from beats, not 99
        assert out["tempo_confidence"] > 0.9

    def test_relative_key_flip_happens_after_chords(self, monkeypatch):
        out = self._run(monkeypatch, ["Am", "F", "C", "G", "Am", "Am"])
        assert out["key"] == "A minor"
