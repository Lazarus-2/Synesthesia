"""
Beat + downbeat tracking with a deterministic meter estimate (Phase 5 G2).

Tries madmom's RNN tracker first, but madmom does not install on
Python 3.12, so in practice the librosa onset/beat fallback is what runs.
Either path yields beat *times*; the shared finalizer then samples a
beat-synchronous accent signal and runs :func:`backend.ml.meter.detect_meter`
to assign real downbeat positions (``beat_number`` cycling at the detected
measure length, ``is_downbeat`` true on beat 1) and a song ``time_signature``
— replacing the old fabricated ``beat_number=(i % 4) + 1`` grid.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 1)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from backend.config import MAX_AUDIO_DURATION_S
from backend.ml.meter import beat_accents, detect_meter
from backend.schemas import BeatEvent

logger = logging.getLogger(__name__)

_HOP_LENGTH = 512
# Downbeats are carried mostly by low-frequency kick/bass energy; onset flux
# is a weaker secondary cue (log-compression flattens loudness). Combine them
# low-band-first when deriving the per-beat accent for meter detection.
_LOW_FREQ_HZ = 150.0
_ONSET_ACCENT_WEIGHT = 0.4


@dataclass(frozen=True)
class BeatTrackingResult:
    """Beats plus the deterministic meter estimate derived from them."""

    beats: list[BeatEvent] = field(default_factory=list)
    time_signature: str = "4/4"
    meter_confidence: float = 0.0


def _beat_accent_signal(y, sr: int, onset_env, beat_frames):
    """Per-beat accent = low-band (kick/bass) energy + a touch of onset flux.

    Downbeats stand out in low-frequency energy far more than in onset flux,
    so the low band leads; onset adds nuance for percussion-light material.
    """
    import librosa
    import numpy as np

    spec = np.abs(librosa.stft(y, hop_length=_HOP_LENGTH)) ** 2
    freqs = librosa.fft_frequencies(sr=sr)
    low_env = spec[freqs < _LOW_FREQ_HZ].sum(axis=0)

    low_acc = beat_accents(low_env, beat_frames)
    onset_acc = beat_accents(onset_env, beat_frames)

    def _norm(a):
        m = float(a.max()) if a.size else 0.0
        return a / m if m > 0 else a

    return _norm(low_acc) + _ONSET_ACCENT_WEIGHT * _norm(onset_acc)


def _assemble(beat_times, y, onset_env, sr: int) -> BeatTrackingResult:
    """Turn beat times + audio features into a meter-aware BeatTrackingResult."""
    import librosa

    if beat_times is None or len(beat_times) == 0:
        return BeatTrackingResult()

    beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=_HOP_LENGTH)
    accents = _beat_accent_signal(y, sr, onset_env, beat_frames)
    meter = detect_meter(accents)

    beats = []
    for i, t in enumerate(beat_times):
        beat_number = ((i - meter.offset) % meter.numerator) + 1
        beats.append(
            BeatEvent(time=float(t), beat_number=beat_number, is_downbeat=(beat_number == 1))
        )
    return BeatTrackingResult(
        beats=beats,
        time_signature=meter.time_signature,
        meter_confidence=meter.confidence,
    )


def track_beats(audio_path: str | Path) -> BeatTrackingResult:
    """Detect beats, downbeats (1..N per measure), and the song's time signature."""
    import librosa

    try:
        y, sr = librosa.load(str(audio_path), sr=22050, duration=MAX_AUDIO_DURATION_S)
    except Exception as e:
        logger.warning("Beat tracking failed to load %s: %s", audio_path, e)
        return BeatTrackingResult()

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=_HOP_LENGTH)

    try:
        # Try madmom if installed (it is not, on py3.12 — falls through).
        from madmom.features.beats import BeatTrackingProcessor, RNNBeatProcessor

        rnn = RNNBeatProcessor()
        tracker = BeatTrackingProcessor(fps=100)
        beat_times = tracker(rnn(str(audio_path)))
    except ImportError:
        try:
            _, beat_frames = librosa.beat.beat_track(
                onset_envelope=onset_env, sr=sr, hop_length=_HOP_LENGTH
            )
            beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=_HOP_LENGTH)
        except Exception as e:
            logger.warning("Beat tracking failed for %s: %s", audio_path, e)
            return BeatTrackingResult()

    return _assemble(beat_times, y, onset_env, sr)
