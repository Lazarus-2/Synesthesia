"""Deterministic meter / downbeat detection (Phase 5 G2).

No trained model — pure numpy DSP, the same license-clean grain as the
Phase-4 chord/key work. Given a beat-synchronous *accent* signal (how
strong each beat is), ``detect_meter`` recovers:

  * the measure length (beats per bar) among common candidates,
  * the downbeat phase (which beat in the cycle is beat 1),
  * a confidence in [0, 1].

It works because a downbeat carries more accent (onset + low-frequency
energy) than the beats around it: the candidate (measure, phase) whose
downbeats stand out most from the off-beats wins. This replaces the
fabricated ``beat_number=(i % 4) + 1`` grid and is the CPU-fallback
contract a trained downbeat tracker (Beat This!/allin1) would slot above.
"""

from __future__ import annotations

from dataclasses import dataclass

# Candidate measure lengths (beats per bar) and their rendered time sig.
TIME_SIGNATURES: dict[int, str] = {2: "2/4", 3: "3/4", 4: "4/4", 6: "6/8"}
_CANDIDATES = (2, 3, 4, 6)

# Mild common-meter prior: nudges near-ties toward 4 then 3 so ambiguous
# signals don't flip to exotic readings. Added to each candidate's contrast.
_METER_PRIOR = {4: 0.04, 3: 0.02, 2: 0.0, 6: 0.0}

# Need at least this many beats to trust a periodicity estimate.
MIN_BEATS_FOR_METER = 8

# Confidence calibration: contrast (downbeat-minus-offbeat accent, on a
# unit-max-normalized accent signal) of this size maps to confidence 1.0.
_CONFIDENCE_FULL_CONTRAST = 0.55


@dataclass(frozen=True)
class MeterResult:
    numerator: int
    offset: int
    time_signature: str
    confidence: float


def beat_accents(onset_env, beat_frames) -> "object":
    """Sample the onset envelope at each beat (peak in a short look-ahead).

    A downbeat's onset peak can land a frame or two after the tracked beat,
    so we take the max of a tiny window starting at the beat frame.
    """
    import numpy as np

    onset = np.asarray(onset_env, dtype=float)
    frames = np.asarray(beat_frames, dtype=int)
    if frames.size == 0:
        return np.zeros(0)
    window = 3
    out = np.empty(frames.size, dtype=float)
    for i, f in enumerate(frames):
        f = max(0, min(int(f), onset.size - 1))
        out[i] = float(onset[f : min(onset.size, f + window)].max())
    return out


def detect_meter(accents, candidates: tuple[int, ...] = _CANDIDATES) -> MeterResult:
    """Recover (numerator, downbeat offset, time signature, confidence).

    ``accents`` is one non-negative value per beat. Degenerate input
    (too few beats, flat/zero accents) returns the 4/4 default at
    confidence 0.0.
    """
    import numpy as np

    a = np.asarray(accents, dtype=float).reshape(-1)
    default = MeterResult(numerator=4, offset=0, time_signature="4/4", confidence=0.0)
    if a.size < MIN_BEATS_FOR_METER:
        return default

    peak = a.max()
    if peak <= 0:
        return default
    a = a / peak  # scale-invariant; accents now in [0, 1]
    if a.std() < 1e-6:
        return default  # flat — no downbeat structure

    best = None  # (adjusted_score, raw_contrast, numerator, offset)
    for m in candidates:
        if a.size < 2 * m:
            continue  # need at least two full measures to judge period m
        for p in range(m):
            mask = ((np.arange(a.size) - p) % m) == 0
            if not mask.any() or mask.all():
                continue
            contrast = float(a[mask].mean() - a[~mask].mean())
            adjusted = contrast + _METER_PRIOR.get(m, 0.0)
            if best is None or adjusted > best[0]:
                best = (adjusted, contrast, m, p)

    if best is None:
        return default

    _, contrast, numerator, offset = best
    confidence = float(np.clip(contrast / _CONFIDENCE_FULL_CONTRAST, 0.0, 1.0))
    confidence = round(confidence, 3)
    return MeterResult(
        numerator=numerator,
        offset=offset,
        time_signature=TIME_SIGNATURES.get(numerator, "4/4"),
        confidence=confidence,
    )
