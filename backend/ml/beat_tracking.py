"""
Beat tracking. Returns beat times + downbeats for measure detection.

Tries madmom's RNN tracker first, but madmom does not install on
Python 3.12, so in practice the librosa onset/beat fallback is what runs.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 1)
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.config import MAX_AUDIO_DURATION_S
from backend.schemas import BeatEvent

logger = logging.getLogger(__name__)


def track_beats(audio_path: str | Path) -> list[BeatEvent]:
    """Detect beats and their position within the measure (1,2,3,4)."""
    try:
        # Try to use madmom if installed
        from madmom.features.beats import BeatTrackingProcessor, RNNBeatProcessor

        rnn = RNNBeatProcessor()
        tracker = BeatTrackingProcessor(fps=100)
        activations = rnn(str(audio_path))
        times = tracker(activations)
        return [BeatEvent(time=t, beat_number=(i % 4) + 1) for i, t in enumerate(times)]
    except ImportError:
        # Robust fallback using librosa
        import librosa

        try:
            y, sr = librosa.load(str(audio_path), sr=22050, duration=MAX_AUDIO_DURATION_S)
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            tempo, beats_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            times = librosa.frames_to_time(beats_frames, sr=sr)
            return [BeatEvent(time=float(t), beat_number=(i % 4) + 1) for i, t in enumerate(times)]
        except Exception as e:
            logger.warning("Beat tracking failed for %s: %s", audio_path, e)
            return []
