"""
Chord detection via librosa CQT chromagram + weighted template matching.

84 templates — maj, min, dom7, maj7, min7, dim, sus4 across 12 roots —
scored by cosine similarity (vectorized), majority-vote smoothed, then
segmented into ChordEvents. sus2/dim7/6th templates are deliberately
absent: their pitch-class sets alias other chords in the bank
(sus2(C) == sus4(G); dim7 is 4-fold rotationally symmetric; C6 == Am7).

Usage:
    events = detect_chords("song.mp3")
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.config import MAX_AUDIO_DURATION_S
from backend.schemas import ChordEvent

logger = logging.getLogger(__name__)

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Quality suffix -> weighted (interval, weight) pairs. Root and the
# quality-defining tones (3rd/4th/7th, the dim 5th) weigh 1.0-0.9; the
# plain 5th weighs less because nearly every quality shares it.
QUALITIES: dict[str, tuple[tuple[int, float], ...]] = {
    "": ((0, 1.0), (4, 1.0), (7, 0.7)),
    "m": ((0, 1.0), (3, 1.0), (7, 0.7)),
    "7": ((0, 1.0), (4, 1.0), (7, 0.6), (10, 0.9)),
    "maj7": ((0, 1.0), (4, 1.0), (7, 0.6), (11, 0.9)),
    "m7": ((0, 1.0), (3, 1.0), (7, 0.6), (10, 0.9)),
    "dim": ((0, 1.0), (3, 1.0), (6, 0.9)),
    "sus4": ((0, 1.0), (5, 1.0), (7, 0.7)),
}

NC_LABEL = "N.C."
# Frames whose harmonic-residual RMS sits below this are silence: chroma_cqt
# max-normalizes every frame, so silence is invisible in the chroma itself.
NC_RMS_THRESHOLD = 1e-3
# Best cosine below this means "no template fits" (uniform chroma peaks ~0.57).
NC_SCORE_THRESHOLD = 0.6
# dom7 may only beat maj when the b7 bin carries at least this fraction of the
# root bin's energy — real instruments leak energy near b7 via the 7th partial.
DOM7_B7_MIN_RATIO = 0.5

_SMOOTHING_WINDOW = 15

# Beat-sync quality gate: librosa's tracker (madmom is absent on py3.12) can
# return sparse or degenerate beats; below these floors we decode frame-level.
MIN_BEATS_FOR_SYNC = 8
_BEAT_INTERVAL_RANGE_S = (0.2, 2.0)  # 30-300 BPM


def build_chord_templates():
    """Return (names, matrix): 84 labels + row-unit-normalized (84, 12) bank.

    Ordering is fixed (quality-major, chromatic roots within each quality) so
    argmax tie-breaking is deterministic across processes.
    """
    import numpy as np

    names: list[str] = []
    rows = []
    for suffix, weighted in QUALITIES.items():
        for root in range(12):
            vec = np.zeros(12)
            for interval, weight in weighted:
                vec[(root + interval) % 12] = weight
            names.append(f"{NOTES[root]}{suffix}")
            rows.append(vec / np.linalg.norm(vec))
    return names, np.array(rows)


def classify_frames(chroma, rms=None) -> list[tuple[str, float]]:
    """Classify each chroma frame -> (label, confidence in [0, 1]).

    ``chroma`` is (12, n_frames); ``rms`` is an optional per-frame energy
    array used to force N.C. on silent frames. Confidence is the plain
    cosine between the unit chroma and the unit template (single
    normalization — see ML-08 in docs/audit/PHASE4_PREFLIGHT_AUDIT.md).
    """
    import numpy as np

    names, templates = build_chord_templates()
    chroma = np.asarray(chroma, dtype=float)
    n_frames = chroma.shape[1]

    norms = np.linalg.norm(chroma, axis=0)
    valid = norms > 1e-9
    unit = np.zeros_like(chroma)
    unit[:, valid] = chroma[:, valid] / norms[valid]

    scores = templates @ unit  # (84, n_frames)
    best_idx = scores.argmax(axis=0)

    # dom7 guard: demote dom7 picks whose b7 evidence is too weak.
    quality_of = np.array([_suffix_of(name) for name in names])
    roots = np.array([NOTES.index(_root_of(name)) for name in names])
    dom7_picked = np.flatnonzero(quality_of[best_idx] == "7")
    if dom7_picked.size:
        picked_roots = roots[best_idx[dom7_picked]]
        b7_bins = (picked_roots + 10) % 12
        root_energy = chroma[picked_roots, dom7_picked]
        b7_energy = chroma[b7_bins, dom7_picked]
        weak = dom7_picked[b7_energy < DOM7_B7_MIN_RATIO * root_energy]
        if weak.size:
            non_dom7 = scores.copy()
            non_dom7[quality_of == "7", :] = -np.inf
            best_idx[weak] = non_dom7[:, weak].argmax(axis=0)

    best_scores = scores[best_idx, np.arange(n_frames)]
    confidences = np.clip(best_scores, 0.0, 1.0)

    nc = ~valid | (best_scores < NC_SCORE_THRESHOLD)
    if rms is not None:
        rms = np.asarray(rms, dtype=float).reshape(-1)[:n_frames]
        nc[: rms.shape[0]] |= rms < NC_RMS_THRESHOLD

    return [
        (NC_LABEL, 0.0) if nc[t] else (names[best_idx[t]], float(confidences[t]))
        for t in range(n_frames)
    ]


def _beats_are_sane(beat_times: list[float], duration: float) -> bool:
    """True when beats are dense, monotonic, and at a plausible musical rate."""
    if len(beat_times) < MIN_BEATS_FOR_SYNC:
        return False
    intervals = [b - a for a, b in zip(beat_times, beat_times[1:])]
    if any(iv <= 0 for iv in intervals):
        return False
    if duration > 0 and (beat_times[-1] - beat_times[0]) < 0.25 * duration:
        return False  # beats cover too little of the clip to trust
    median = sorted(intervals)[len(intervals) // 2]
    lo, hi = _BEAT_INTERVAL_RANGE_S
    return lo <= median <= hi


def classify_beat_segments(chroma, beat_times, time_per_frame: float, rms=None):
    """Average chroma between beat boundaries and classify each segment.

    Beat times are snapped to the frame grid; out-of-range or duplicate
    boundaries collapse away. Returns ``(labeled, boundaries)`` where
    ``labeled`` is one ``(label, confidence)`` per segment and
    ``boundaries`` has ``len(labeled) + 1`` ascending times covering the
    whole clip.
    """
    import numpy as np

    chroma = np.asarray(chroma, dtype=float)
    n_frames = chroma.shape[1]
    duration = n_frames * time_per_frame

    cuts = {int(round(t / time_per_frame)) for t in beat_times if 0.0 < t < duration}
    frame_bounds = sorted({0, n_frames} | {c for c in cuts if 0 < c < n_frames})

    seg_chroma = np.stack(
        [chroma[:, a:b].mean(axis=1) for a, b in zip(frame_bounds, frame_bounds[1:])],
        axis=1,
    )
    seg_rms = None
    if rms is not None:
        rms = np.asarray(rms, dtype=float).reshape(-1)
        seg_rms = np.array(
            [rms[a : min(b, rms.shape[0])].mean() if a < rms.shape[0] else 0.0
             for a, b in zip(frame_bounds, frame_bounds[1:])]
        )

    # No cross-segment smoothing here: per-beat chroma averaging already
    # smooths within the beat, and a majority window would erase real
    # one-beat chords.
    labeled = classify_frames(seg_chroma, rms=seg_rms)
    boundaries = [f * time_per_frame for f in frame_bounds]
    return labeled, boundaries


def _root_of(name: str) -> str:
    return name[:2] if len(name) > 1 and name[1] == "#" else name[:1]


def _suffix_of(name: str) -> str:
    return name[len(_root_of(name)) :]


def _smooth_frames(
    frame_chords: list[tuple[str, float]], window_size: int = _SMOOTHING_WINDOW
) -> list[tuple[str, float]]:
    """Majority-vote smoothing; ties break to the earliest label in the window."""
    n = len(frame_chords)
    half_w = window_size // 2
    smoothed: list[tuple[str, float]] = []
    for i in range(n):
        neighbors = frame_chords[max(0, i - half_w) : min(n, i + half_w + 1)]
        neighbor_chords = [c for c, _ in neighbors]
        counts: dict[str, int] = {}
        for c in neighbor_chords:
            counts[c] = counts.get(c, 0) + 1
        # max() keeps the first-seen key on count ties (insertion order).
        most_common = max(counts, key=counts.get)
        matching = [s for c, s in neighbors if c == most_common]
        smoothed.append((most_common, sum(matching) / len(matching)))
    return smoothed


def _segments_to_events(
    labeled: list[tuple[str, float]], boundaries: list[float]
) -> list[ChordEvent]:
    """Merge consecutive same-label segments into ChordEvents."""
    from backend.tools.synesthesia_colors import get_chord_color

    events: list[ChordEvent] = []
    if not labeled:
        return events

    curr_chord, _ = labeled[0]
    start_time = boundaries[0]
    conf_accum: list[float] = []

    for i, (chord, conf) in enumerate(labeled):
        if chord != curr_chord:
            events.append(
                ChordEvent(
                    start=float(start_time),
                    end=float(boundaries[i]),
                    chord=curr_chord,
                    confidence=round(sum(conf_accum) / len(conf_accum), 3),
                    color=get_chord_color(curr_chord),
                )
            )
            curr_chord = chord
            start_time = boundaries[i]
            conf_accum = [conf]
        else:
            conf_accum.append(conf)

    events.append(
        ChordEvent(
            start=float(start_time),
            end=float(boundaries[-1]),
            chord=curr_chord,
            confidence=round(sum(conf_accum) / len(conf_accum), 3),
            color=get_chord_color(curr_chord),
        )
    )
    return events


def detect_chords(
    audio_path: str | Path, beats: list[float] | None = None
) -> list[ChordEvent]:
    """Return the song's ChordEvents via template matching on CQT chroma.

    When ``beats`` (ascending beat times from the beat tracker) pass the
    sanity gate, chroma is averaged per beat segment and events land on
    beat boundaries; otherwise the frame-level path with majority-vote
    smoothing runs.
    """
    import librosa

    hop_length = 512
    try:
        y, sr = librosa.load(str(audio_path), sr=22050, duration=MAX_AUDIO_DURATION_S)
        y_harmonic, _ = librosa.effects.hpss(y)
        chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr, hop_length=hop_length)
        rms = librosa.feature.rms(y=y_harmonic, hop_length=hop_length)[0]
    except Exception as e:
        logger.warning("Chord detection failed for %s: %s", audio_path, e)
        return []

    num_frames = chroma.shape[1]
    time_per_frame = hop_length / sr
    duration = num_frames * time_per_frame

    if beats and _beats_are_sane(beats, duration):
        labeled, boundaries = classify_beat_segments(
            chroma, beats, time_per_frame, rms=rms
        )
    else:
        if beats:
            logger.info(
                "Beat-sync gate rejected %d beats for %s; frame-level decode",
                len(beats),
                audio_path,
            )
        labeled = _smooth_frames(classify_frames(chroma, rms=rms))
        boundaries = [i * time_per_frame for i in range(num_frames + 1)]

    return _segments_to_events(labeled, boundaries)
