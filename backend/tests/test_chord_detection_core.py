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
    MIN_BEATS_FOR_SYNC,
    NC_LABEL,
    NC_RMS_THRESHOLD,
    NC_SCORE_THRESHOLD,
    NOTES,
    QUALITIES,
    _beats_are_sane,
    _smooth_frames,
    build_chord_templates,
    classify_beat_segments,
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


class TestBeatSync:
    """Phase 4 G2 — beat-synchronous decoding (pure chroma, no audio)."""

    def _two_chord_chroma(self, n_frames: int = 100, switch: int = 50) -> np.ndarray:
        """C major for frames [0, switch), G7 for [switch, n_frames)."""
        c = _chroma_for(0, QUALITY_TONES[""])
        g7 = _chroma_for(7, QUALITY_TONES["7"])
        return np.hstack([c] * switch + [g7] * (n_frames - switch))

    def test_segments_follow_beat_boundaries(self):
        chroma = self._two_chord_chroma()
        beats = [float(i) for i in range(1, 10)]  # 1.0..9.0s over a 10s clip
        labeled, bounds = classify_beat_segments(chroma, beats, time_per_frame=0.1)
        assert len(labeled) == 10
        assert len(bounds) == 11
        np.testing.assert_allclose(bounds, [float(i) for i in range(11)], atol=0.05)
        labels = [label for label, _ in labeled]
        assert labels[:5] == ["C"] * 5
        assert labels[5:] == ["G7"] * 5

    def test_single_beat_passing_chord_survives(self):
        # A one-beat V chord is musically real: the beat path must NOT smear
        # it away the way the 15-frame majority smoother would.
        c = _chroma_for(0, QUALITY_TONES[""])
        g7 = _chroma_for(7, QUALITY_TONES["7"])
        chroma = np.hstack([c] * 30 + [g7] * 10 + [c] * 60)
        beats = [float(i) for i in range(1, 10)]
        labeled, _ = classify_beat_segments(chroma, beats, time_per_frame=0.1)
        labels = [label for label, _ in labeled]
        assert labels[3] == "G7"
        assert labels[:3] == ["C"] * 3 and labels[4:] == ["C"] * 6

    def test_silent_beat_segments_become_nc(self):
        chroma = np.hstack([_chroma_for(0, QUALITY_TONES[""])] * 100)
        rms = np.concatenate([np.full(50, 0.2), np.full(50, NC_RMS_THRESHOLD / 10)])
        beats = [float(i) for i in range(1, 10)]
        labeled, _ = classify_beat_segments(chroma, beats, time_per_frame=0.1, rms=rms)
        labels = [label for label, _ in labeled]
        assert labels[:5] == ["C"] * 5
        assert labels[5:] == [NC_LABEL] * 5

    def test_out_of_range_and_duplicate_beats_are_tolerated(self):
        chroma = self._two_chord_chroma()
        beats = [-1.0, 0.0, 2.0, 2.0, 2.001, 5.0, 99.0]  # junk in, clean out
        labeled, bounds = classify_beat_segments(chroma, beats, time_per_frame=0.1)
        assert bounds[0] == 0.0
        assert bounds[-1] == pytest.approx(10.0)
        assert all(b2 > b1 for b1, b2 in zip(bounds, bounds[1:]))
        assert len(labeled) == len(bounds) - 1

    def test_beats_sanity_gate(self):
        good = [0.5 * i for i in range(1, 21)]  # 20 beats @ 120 BPM
        assert _beats_are_sane(good, duration=12.0)
        assert not _beats_are_sane(good[: MIN_BEATS_FOR_SYNC - 1], duration=12.0)
        assert not _beats_are_sane([], duration=12.0)
        non_monotonic = list(good)
        non_monotonic[5] = non_monotonic[3]
        assert not _beats_are_sane(non_monotonic, duration=12.0)
        too_fast = [0.01 * i for i in range(1, 50)]  # 6000 BPM
        assert not _beats_are_sane(too_fast, duration=12.0)
        too_slow = [4.0 * i for i in range(1, 12)]  # 15 BPM
        assert not _beats_are_sane(too_slow, duration=48.0)


class TestFeaturesNodeBeatThreading:
    def test_features_node_passes_beat_times_to_detect_chords(self, monkeypatch):
        from backend.graph import nodes
        from backend.schemas import BeatEvent

        captured: dict = {}

        def fake_detect(path, beats=None):
            captured["beats"] = beats
            return []

        from backend.ml.key_estimation import KeyTempoResult

        monkeypatch.setattr(
            "backend.ml.key_estimation.estimate_key_and_tempo",
            lambda _p: KeyTempoResult("C major", 0.8, 120.0, 0.4),
        )
        from backend.ml.beat_tracking import BeatTrackingResult

        monkeypatch.setattr(
            "backend.ml.beat_tracking.track_beats",
            lambda _p: BeatTrackingResult(
                beats=[
                    BeatEvent(time=0.5, beat_number=1, is_downbeat=True),
                    BeatEvent(time=1.0, beat_number=2),
                ],
                time_signature="4/4",
                meter_confidence=0.9,
            ),
        )
        monkeypatch.setattr("backend.ml.chord_detection.detect_chords", fake_detect)
        monkeypatch.setattr("backend.ml.structure_detection.detect_sections", lambda _p: [])

        nodes.features_node({"audio_path": "song.mp3", "retries": 0})
        assert captured["beats"] == [0.5, 1.0]

    def test_features_node_passes_none_when_no_beats(self, monkeypatch):
        from backend.graph import nodes

        captured: dict = {}

        def fake_detect(path, beats=None):
            captured["beats"] = beats
            return []

        from backend.ml.key_estimation import KeyTempoResult

        monkeypatch.setattr(
            "backend.ml.key_estimation.estimate_key_and_tempo",
            lambda _p: KeyTempoResult("C major", 0.8, 120.0, 0.4),
        )
        from backend.ml.beat_tracking import BeatTrackingResult

        monkeypatch.setattr(
            "backend.ml.beat_tracking.track_beats", lambda _p: BeatTrackingResult()
        )
        monkeypatch.setattr("backend.ml.chord_detection.detect_chords", fake_detect)
        monkeypatch.setattr("backend.ml.structure_detection.detect_sections", lambda _p: [])

        nodes.features_node({"audio_path": "song.mp3", "retries": 0})
        assert captured["beats"] is None


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
