"""
Key + tempo estimation with librosa, with calibrated confidences (Phase 4 G4).

Key: Krumhansl-Schmuckler chroma correlation over all 24 keys; confidence
combines the absolute best correlation (fit) with the z-scored top-2 margin
(separation). Silent fallbacks and NaN correlations yield confidence 0.0.

Tempo: librosa's onset estimate is only the fallback — ``refine_tempo``
recomputes from the beat tracker's median interval (the same beats the UI
renders), octave-folds into a sane range when the grid is consistent, and
derives confidence from beat-interval consistency.

Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 1)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backend.config import MAX_AUDIO_DURATION_S
from backend.tools.music_constants import FLAT_TO_SHARP_KEYS as _FLAT_TO_SHARP
from backend.tools.music_constants import NOTES as _NOTES


@dataclass(frozen=True)
class KeyTempoResult:
    """Key/tempo estimates with calibrated confidences in [0, 1]."""

    key: str
    key_confidence: float
    tempo: float
    tempo_confidence: float


# --- Key-confidence calibration (probe-tuned on synthetic chroma) ---------
# best-correlation fit term: 0.5 -> 0.0, 0.9 -> 1.0
_BEST_CORR_FLOOR = 0.5
_BEST_CORR_SPAN = 0.4
# top-2 margin in sigma units saturates at 1.5
_MARGIN_Z_SPAN = 1.5
_FIT_WEIGHT, _MARGIN_WEIGHT = 0.7, 0.3

# --- Tempo refinement ------------------------------------------------------
MIN_BEATS_FOR_TEMPO = 8
TEMPO_FOLD_RANGE = (70.0, 180.0)
# octave folding only when the beat grid is consistent (cv below this)
_FOLD_CV_MAX = 0.2
# fallback tempo confidence for the single unverified librosa estimate
_FALLBACK_TEMPO_CONFIDENCE = 0.4

_KEY_RE = re.compile(r"^([A-G][b#]?)\s+(major|minor)$", re.IGNORECASE)

# Chord qualities counted as minor/major tonic evidence (dim/aug/sus are
# ambiguous about mode and are skipped).
_MINOR_QUALITIES = frozenset({"min", "min7", "min9", "min11", "min13"})
_MAJOR_QUALITIES = frozenset(
    {"maj", "maj7", "maj9", "maj11", "maj13", "dom7", "6", "9", "11", "13", "add9"}
)


def estimate_key_and_tempo(audio_path: str | Path) -> KeyTempoResult:
    """Estimate key + tempo with confidences. Never raises; fallbacks score 0.0."""
    import librosa
    import numpy as np

    try:
        y, sr = librosa.load(str(audio_path), sr=22050, duration=MAX_AUDIO_DURATION_S)
    except Exception:
        return KeyTempoResult("C major", 0.0, 120.0, 0.0)

    # 1. Tempo (fallback estimate — features_node refines it from real beats)
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
        tempo_val = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
        tempo_conf = _FALLBACK_TEMPO_CONFIDENCE if tempo_val > 0 else 0.0
        if tempo_val <= 0:
            tempo_val = 120.0
    except Exception:
        tempo_val, tempo_conf = 120.0, 0.0

    # 2. Key via Krumhansl-Schmuckler over the song-mean chroma
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
        key, key_conf = _krumhansl_schmuckler(chroma)
    except Exception:
        key, key_conf = "C major", 0.0

    return KeyTempoResult(key, key_conf, tempo_val, tempo_conf)


def _krumhansl_schmuckler(chroma_vec) -> tuple[str, float]:
    """Correlate chroma with K-S profiles -> (key_name, confidence in [0,1]).

    Confidence = 0.7 * fit + 0.3 * separation, where fit rescales the winning
    Pearson correlation from [0.5, 0.9] and separation is the top-2 margin in
    units of the std-dev of all 24 correlations (saturating at 1.5 sigma).
    NaN correlations (e.g. constant chroma) return ("C major", 0.0).
    """
    import numpy as np

    major_profile = np.array(
        [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    )
    minor_profile = np.array(
        [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    )

    chroma_vec = np.asarray(chroma_vec, dtype=float)
    if chroma_vec.std() < 1e-12:
        return "C major", 0.0

    corrs: list[float] = []
    names: list[str] = []
    for i in range(12):
        for profile, mode in ((major_profile, "major"), (minor_profile, "minor")):
            corrs.append(float(np.corrcoef(chroma_vec, np.roll(profile, i))[0, 1]))
            names.append(f"{_NOTES[i]} {mode}")

    arr = np.array(corrs)
    if np.isnan(arr).any():
        return "C major", 0.0

    order = np.argsort(arr)
    best_i, second_i = order[-1], order[-2]
    best, second = arr[best_i], arr[second_i]
    std = arr.std()
    if std < 1e-9:
        return "C major", 0.0

    fit = np.clip((best - _BEST_CORR_FLOOR) / _BEST_CORR_SPAN, 0.0, 1.0)
    margin = np.clip(((best - second) / std) / _MARGIN_Z_SPAN, 0.0, 1.0)
    confidence = float(_FIT_WEIGHT * fit + _MARGIN_WEIGHT * margin)
    return names[best_i], round(confidence, 3)


def refine_tempo(
    fallback_tempo: float,
    fallback_confidence: float,
    beat_times: list[float] | None,
) -> tuple[float, float]:
    """Tempo from the median beat interval — the same beats the UI renders.

    Octave-folds into ``TEMPO_FOLD_RANGE`` only when the beat grid is
    consistent (cv < 0.2). Confidence = 1 - 4*cv, clamped to [0, 1]. With
    fewer than ``MIN_BEATS_FOR_TEMPO`` beats the fallback estimate (and its
    confidence) is returned unchanged.
    """
    import numpy as np

    if not beat_times or len(beat_times) < MIN_BEATS_FOR_TEMPO:
        return fallback_tempo, fallback_confidence

    intervals = np.diff(np.asarray(beat_times, dtype=float))
    if (intervals <= 0).any():
        return fallback_tempo, fallback_confidence

    median = float(np.median(intervals))
    cv = float(intervals.std() / intervals.mean())
    tempo = 60.0 / median

    if cv < _FOLD_CV_MAX:
        lo, hi = TEMPO_FOLD_RANGE
        while tempo >= hi and tempo / 2 >= lo:
            tempo /= 2
        while tempo < lo and tempo * 2 < hi:
            tempo *= 2

    confidence = float(np.clip(1.0 - 4.0 * cv, 0.0, 1.0))
    return round(tempo, 1), round(confidence, 3)


def disambiguate_relative_key(key_name: str, chord_labels: list[str]) -> str:
    """Tonic-evidence check between a key and its relative (Phase 4 G4).

    Relative keys share every pitch, so chroma correlation cannot separate
    them — but the detected chords can: whichever candidate tonic triad is
    more frequent and frames the song (opening/closing chord) wins. Returns
    the (possibly flipped) key name; anything unparseable passes through.
    """
    from backend.tools.chords import parse_chord

    m = _KEY_RE.match(key_name.strip()) if key_name else None
    if not m:
        return key_name
    root_name, mode = m.group(1), m.group(2).lower()
    root_pc = _pitch_class(root_name)
    if root_pc is None:
        return key_name

    if mode == "major":
        rel_pc, rel_mode = (root_pc + 9) % 12, "minor"
    else:
        rel_pc, rel_mode = (root_pc + 3) % 12, "major"

    tonics: list[tuple[int, bool] | None] = []
    for label in chord_labels:
        if not label or label.upper() in ("N.C.", "N"):
            continue
        parts = parse_chord(label)
        pc = _pitch_class(parts.root) if parts.root else None
        if pc is None:
            continue
        if parts.quality in _MINOR_QUALITIES:
            tonics.append((pc, True))
        elif parts.quality in _MAJOR_QUALITIES:
            tonics.append((pc, False))
        else:
            tonics.append(None)  # dim/aug/sus: keeps first/last positions honest

    if not tonics:
        return key_name

    def score(pc: int, minor: bool) -> int:
        target = (pc, minor)
        s = sum(2 for t in tonics if t == target)
        if tonics[0] == target:
            s += 3
        if tonics[-1] == target:
            s += 4
        return s

    home = score(root_pc, mode == "minor")
    relative = score(rel_pc, rel_mode == "minor")
    if relative > home:
        return f"{_NOTES[rel_pc]} {rel_mode}"
    return key_name


def _pitch_class(note: str | None) -> int | None:
    if not note:
        return None
    n = note.strip().upper()
    n = _FLAT_TO_SHARP.get(n, n)
    try:
        return _NOTES.index(n)
    except ValueError:
        return None
