"""
Beat tracking with madmom. Returns beat times + downbeats for measure detection.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 1)
"""
from __future__ import annotations

from pathlib import Path

from backend.schemas import BeatEvent


def track_beats(audio_path: str | Path) -> list[BeatEvent]:
    """Detect beats and their position within the measure (1,2,3,4)."""
    # TODO(Phase 1):
    # from madmom.features.beats import RNNBeatProcessor, BeatTrackingProcessor
    # rnn = RNNBeatProcessor()
    # tracker = BeatTrackingProcessor(fps=100)
    # activations = rnn(str(audio_path))
    # times = tracker(activations)
    # return [BeatEvent(time=t, beat_number=(i % 4) + 1) for i, t in enumerate(times)]
    raise NotImplementedError("Fill in during Phase 1")
