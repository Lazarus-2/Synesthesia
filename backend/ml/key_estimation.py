"""
Key + tempo estimation with librosa.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 1)
"""
from __future__ import annotations

from pathlib import Path


def estimate_key_and_tempo(audio_path: str | Path) -> tuple[str, float]:
    """Returns (key_name, tempo_bpm). Key is e.g. 'C major' or 'A minor'."""
    # TODO(Phase 1):
    # import librosa
    # import numpy as np
    # y, sr = librosa.load(str(audio_path), sr=22050)
    # tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    # chroma = librosa.feature.chroma_cens(y=y, sr=sr).mean(axis=1)
    # key = _krumhansl_schmuckler(chroma)
    # return key, float(tempo)
    raise NotImplementedError("Fill in during Phase 1")


def _krumhansl_schmuckler(chroma_vec) -> str:
    """Correlate chroma with Krumhansl major/minor profiles."""
    # TODO: implement with Krumhansl key profiles
    # major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    # minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    raise NotImplementedError
