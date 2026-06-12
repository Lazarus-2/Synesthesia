"""Detector-core unit tests for the 84-template chord engine (Phase 4 G1).

Pure-numpy synthetic chroma — no audio, no librosa — so these run in the
default CI selection (deliberately NO ``ml`` marker; see CI-DEAD in
docs/audit/PHASE4_PREFLIGHT_AUDIT.md).
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.ml.chord_detection import (
    DOM7_B7_MIN_RATIO,
    NC_LABEL,
    NC_RMS_THRESHOLD,
    NC_SCORE_THRESHOLD,
    NOTES,
    QUALITIES,
    _smooth_frames,
    build_chord_templates,
    classify_frames,
)


def _chroma_for(root: int, intervals: tuple[int, ...], energy: float = 1.0) -> np.ndarray:
    """A single synthetic chroma frame with equal energy on the chord tones."""
    vec = np.zeros(12)
    for iv in intervals:
        vec[(root + iv) % 12] = energy
    return vec.reshape(12, 1)


# Plain (unweighted) chord-tone sets, per quality suffix.
QUALITY_TONES = {
    "": (0, 4, 7),
    "m": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "dim": (0, 3, 6),
    "sus4": (0, 5, 7),
}


class TestTemplateBank:
    def test_84_templates_with_wellformed_deterministic_labels(self):
        names, matrix = build_chord_templates()
        assert len(names) == 84
        assert matrix.shape == (84, 12)
        assert len(set(names)) == 84
        suffixes = set(QUALITY_TONES)
        for name in names:
            root = name[:2] if len(name) > 1 and name[1] == "#" else name[:1]
            assert root in NOTES, name
            assert name[len(root) :] in suffixes, name
        # Deterministic ordering: two builds agree exactly.
        names2, matrix2 = build_chord_templates()
        assert names == names2
        np.testing.assert_array_equal(matrix, matrix2)

    def test_template_rows_are_unit_normalized(self):
        _, matrix = build_chord_templates()
        np.testing.assert_allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-9)

    def test_quality_definitions_match_expected_vocabulary(self):
        assert set(QUALITIES) == set(QUALITY_TONES)
        for suffix, weighted in QUALITIES.items():
            assert tuple(iv for iv, _ in weighted) == QUALITY_TONES[suffix]


class TestFrameClassification:
    @pytest.mark.parametrize("root", range(12))
    @pytest.mark.parametrize("suffix", sorted(QUALITY_TONES))
    def test_each_template_classifies_its_clean_chroma(self, root: int, suffix: str):
        chroma = _chroma_for(root, QUALITY_TONES[suffix])
        [(label, conf)] = classify_frames(chroma)
        assert label == f"{NOTES[root]}{suffix}"
        assert conf > 0.9

    def test_ml08_perfect_match_confidence_near_one(self):
        # Regression for the double-normalization bug: a frame that exactly
        # matches a template must score ~1.0 regardless of its energy.
        names, matrix = build_chord_templates()
        idx = names.index("C")
        chroma = (matrix[idx] * 7.3).reshape(12, 1)  # arbitrary energy
        [(label, conf)] = classify_frames(chroma)
        assert label == "C"
        assert conf == pytest.approx(1.0, abs=1e-6)

    def test_confidence_invariant_to_global_chroma_scaling(self):
        chroma = _chroma_for(9, QUALITY_TONES["m7"])  # Am7
        base = classify_frames(chroma)
        scaled = classify_frames(chroma * 250.0)
        assert base == scaled

    def test_relative_aliases_resolve_by_present_tones(self):
        # Documented-behavior pair: Em (E,G,B) must NOT be absorbed by Cmaj7,
        # and the full Cmaj7 tetrad must NOT collapse to Em.
        [(em, _)] = classify_frames(_chroma_for(4, QUALITY_TONES["m"]))
        assert em == "Em"
        [(cmaj7, _)] = classify_frames(_chroma_for(0, QUALITY_TONES["maj7"]))
        assert cmaj7 == "Cmaj7"

    def test_multi_frame_input_returns_one_result_per_frame(self):
        frames = np.hstack(
            [
                _chroma_for(0, QUALITY_TONES[""]),
                _chroma_for(7, QUALITY_TONES["7"]),
                _chroma_for(2, QUALITY_TONES["m"]),
            ]
        )
        labels = [label for label, _ in classify_frames(frames)]
        assert labels == ["C", "G7", "Dm"]


class TestDom7Guard:
    def test_weak_b7_leak_stays_major(self):
        # Harmonic leakage at the 7th partial: a C triad with a faint Bb must
        # remain "C", not flip to "C7".
        chroma = _chroma_for(0, (0, 4, 7))
        chroma[10, 0] = DOM7_B7_MIN_RATIO * 0.5  # well below the guard
        [(label, _)] = classify_frames(chroma)
        assert label == "C"

    def test_strong_b7_is_dom7(self):
        chroma = _chroma_for(0, (0, 4, 7))
        chroma[10, 0] = 0.9
        [(label, _)] = classify_frames(chroma)
        assert label == "C7"


class TestNoChordGuards:
    def test_zero_chroma_is_nc(self):
        [(label, conf)] = classify_frames(np.zeros((12, 1)))
        assert (label, conf) == (NC_LABEL, 0.0)

    def test_flat_noise_chroma_is_nc(self):
        # Uniform chroma (what silence looks like after chroma_cqt's per-frame
        # max-normalization) must score below the floor and become N.C.
        [(label, conf)] = classify_frames(np.ones((12, 1)))
        assert (label, conf) == (NC_LABEL, 0.0)
        assert NC_SCORE_THRESHOLD > 0.57  # flat chroma's best cosine ~0.568

    def test_silent_rms_frame_is_nc_even_with_chordal_chroma(self):
        chroma = _chroma_for(0, QUALITY_TONES[""])
        rms = np.array([NC_RMS_THRESHOLD / 10.0])
        [(label, conf)] = classify_frames(chroma, rms=rms)
        assert (label, conf) == (NC_LABEL, 0.0)

    def test_loud_rms_frame_keeps_its_chord(self):
        chroma = _chroma_for(0, QUALITY_TONES[""])
        rms = np.array([0.2])
        [(label, _)] = classify_frames(chroma, rms=rms)
        assert label == "C"


class TestSmoothingDeterminism:
    def test_majority_vote_tie_breaks_to_earliest_in_window(self):
        frames = [("C", 1.0), ("Dm", 1.0)]
        smoothed = _smooth_frames(frames, window_size=2)
        assert [label for label, _ in smoothed] == ["C", "C"]

    def test_majority_wins_over_flicker(self):
        frames = [("C", 0.9)] * 6 + [("G", 0.9)] + [("C", 0.9)] * 6
        smoothed = _smooth_frames(frames, window_size=5)
        assert {label for label, _ in smoothed} == {"C"}

    def test_repeated_runs_are_identical(self):
        frames = [("C", 1.0), ("Am", 1.0), ("F", 1.0), ("G", 1.0)] * 3
        assert _smooth_frames(frames, window_size=4) == _smooth_frames(frames, window_size=4)
