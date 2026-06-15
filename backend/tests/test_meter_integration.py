"""Phase 5 G1/G2 — meter detection on real synthesized audio (ml-marked).

These exercise the full onset-envelope -> beat_accents -> detect_meter path
on librosa-computed features from generated click tracks with accented
downbeats — the regression net the deterministic unit tests in
test_meter.py can't cover (they feed accent arrays directly).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.ml
pytest.importorskip("librosa")

from backend.tests.conftest import make_click_track_wav  # noqa: E402


def _accents_at_true_beats(wav: Path, bpm: int, n_beats: int):
    """Production accent signal sampled at the KNOWN beat times of a click track.

    Isolates the accent->meter path from librosa's own beat-tracking
    uncertainty (which can lock to a tempo multiple on bare clicks) while
    still exercising the real low-band+onset accent extraction.
    """
    import librosa

    from backend.ml.beat_tracking import _beat_accent_signal

    y, sr = librosa.load(str(wav), sr=22050)
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    spb = 60.0 / bpm
    true_times = [i * spb for i in range(n_beats)]
    frames = librosa.time_to_frames(true_times, sr=sr, hop_length=512)
    return _beat_accent_signal(y, sr, onset, frames)


class TestMeterFromRealOnsets:
    @pytest.mark.parametrize(
        "numerator,sig", [(2, "2/4"), (3, "3/4"), (4, "4/4"), (6, "6/8")]
    )
    def test_detects_meter_from_click_track(self, tmp_path, numerator, sig):
        from backend.ml.meter import detect_meter

        n_measures = 8
        n_beats = n_measures * numerator
        wav = tmp_path / f"click_{numerator}.wav"
        make_click_track_wav(wav, bpm=120, numerator=numerator, n_measures=n_measures)

        accents = _accents_at_true_beats(wav, bpm=120, n_beats=n_beats)
        result = detect_meter(accents)
        assert result.numerator == numerator, (numerator, result)
        assert result.time_signature == sig
        assert result.confidence > 0.3


class TestTrackBeatsEndToEnd:
    def test_track_beats_returns_meter_aware_result(self, tmp_path):
        from backend.ml.beat_tracking import BeatTrackingResult, track_beats

        wav = tmp_path / "click_4.wav"
        make_click_track_wav(wav, bpm=120, numerator=4, n_measures=8)

        result = track_beats(wav)
        assert isinstance(result, BeatTrackingResult)
        assert result.time_signature in {"2/4", "3/4", "4/4", "6/8"}
        assert 0.0 <= result.meter_confidence <= 1.0
        assert result.beats, "expected beats from a clean click track"
        # is_downbeat is consistent with beat_number cycling.
        for b in result.beats:
            assert b.is_downbeat == (b.beat_number == 1)
        # At least one downbeat detected.
        assert any(b.is_downbeat for b in result.beats)

    def test_empty_audio_degrades_gracefully(self, tmp_path):
        import wave

        from backend.ml.beat_tracking import track_beats

        empty = tmp_path / "empty.wav"
        with wave.open(str(empty), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"")
        result = track_beats(empty)
        assert result.beats == []
        assert result.time_signature == "4/4"
        assert result.meter_confidence == 0.0
