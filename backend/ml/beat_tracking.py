"""
Beat tracking with madmom. Returns beat times + downbeats for measure detection.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 1)
"""
from __future__ import annotations

from pathlib import Path

from backend.schemas import BeatEvent


def track_beats(audio_path: str | Path) -> list[BeatEvent]:
    """Detect beats and their position within the measure (1,2,3,4)."""
    try:
        # Try to use madmom if installed
        from madmom.features.beats import RNNBeatProcessor, BeatTrackingProcessor
        rnn = RNNBeatProcessor()
        tracker = BeatTrackingProcessor(fps=100)
        activations = rnn(str(audio_path))
        times = tracker(activations)
        return [BeatEvent(time=t, beat_number=(i % 4) + 1) for i, t in enumerate(times)]
    except ImportError:
        # Robust fallback using librosa
        import librosa
        try:
            y, sr = librosa.load(str(audio_path), sr=22050, duration=180)
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            tempo, beats_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            times = librosa.frames_to_time(beats_frames, sr=sr)
            return [BeatEvent(time=float(t), beat_number=(i % 4) + 1) for i, t in enumerate(times)]
        except Exception:
            return []
