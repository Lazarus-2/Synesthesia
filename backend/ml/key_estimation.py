"""
Key + tempo estimation with librosa.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 1)
"""

from __future__ import annotations

from pathlib import Path


def estimate_key_and_tempo(audio_path: str | Path) -> tuple[str, float]:
    """Returns (key_name, tempo_bpm). Key is e.g. 'C major' or 'A minor'."""
    import librosa
    import numpy as np

    try:
        # Load audio (downsample to 22050Hz for speed)
        y, sr = librosa.load(
            str(audio_path), sr=22050, duration=180
        )  # limit to first 3 mins for speed
    except Exception:
        # Graceful fallback if loading fails
        return "C major", 120.0

    # 1. Estimate tempo
    try:
        # For librosa >= 0.10, beat_track returns (tempo_array, beats) or float depending on args
        # We can use librosa.feature.onset_envelope + librosa.beat.beat_track
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
        # Handle case where tempo is a numpy array
        if isinstance(tempo, np.ndarray):
            tempo_val = float(tempo[0])
        else:
            tempo_val = float(tempo)
    except Exception:
        tempo_val = 120.0

    # 2. Estimate key using CQT Chroma and Krumhansl-Schmuckler profiles
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
        key = _krumhansl_schmuckler(chroma)
    except Exception:
        key = "C major"

    return key, tempo_val


def _krumhansl_schmuckler(chroma_vec) -> str:
    """Correlate chroma with Krumhansl major/minor profiles."""
    import numpy as np

    major_profile = np.array(
        [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    )
    minor_profile = np.array(
        [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    )

    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    best_corr = -1.0
    best_key = "C major"

    for i in range(12):
        # Shift profiles cyclically
        shifted_major = np.roll(major_profile, i)
        shifted_minor = np.roll(minor_profile, i)

        # Compute Pearson correlation
        corr_major = np.corrcoef(chroma_vec, shifted_major)[0, 1]
        corr_minor = np.corrcoef(chroma_vec, shifted_minor)[0, 1]

        if corr_major > best_corr:
            best_corr = corr_major
            best_key = f"{notes[i]} major"

        if corr_minor > best_corr:
            best_corr = corr_minor
            best_key = f"{notes[i]} minor"

    return best_key
