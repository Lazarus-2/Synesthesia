"""Coarse song structure detection (Plan 3 B2).

Splits an audio file into sections (Intro / Verse / Chorus / Bridge /
Outro) by clustering repeating chroma patterns. Uses ``librosa``'s
self-similarity matrix + segment-level agglomerative clustering, which is
deterministic, fast (~hundreds of ms for a 3-minute song), and adequate
for the UI's "section ribbon" without needing an ML model.

The schema and frontend ribbon already exist
(:class:`backend.schemas.SongSection`, ``WaveformPlayer.tsx``); this
module is the missing detection step that fills them in.
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.config import MAX_AUDIO_DURATION_S
from backend.schemas import SongSection

logger = logging.getLogger(__name__)


def _label_section(idx: int, label: int, all_labels: list[int]) -> str:
    """Translate cluster indices to friendly names.

    Heuristic: the cluster appearing most often (and longest) is the chorus;
    the second-most-common is the verse; the first segment is intro; the
    last is outro; everything else is "bridge".
    """
    counts: dict[int, int] = {}
    for lbl in all_labels:
        counts[lbl] = counts.get(lbl, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    chorus_label = ordered[0][0] if ordered else None
    verse_label = ordered[1][0] if len(ordered) > 1 else None

    if idx == 0 and len(all_labels) > 1:
        return "Intro"
    if idx == len(all_labels) - 1 and len(all_labels) > 1:
        return "Outro"
    if label == chorus_label:
        return "Chorus"
    if label == verse_label:
        return "Verse"
    return "Bridge"


def detect_sections(
    audio_path: str | Path,
    *,
    target_segments: int = 6,
) -> list[SongSection]:
    """Detect song sections; returns SongSection list (may be empty).

    Approach: librosa CQT chroma → self-similarity → agglomerative
    boundaries → cluster boundaries by chroma similarity → label by
    frequency heuristic.
    """
    try:
        import librosa
        import numpy as np
    except Exception as e:
        logger.warning("structure_detection: librosa unavailable (%s)", e)
        return []

    try:
        y, sr = librosa.load(str(audio_path), sr=22050, duration=MAX_AUDIO_DURATION_S)
        if y.size == 0:
            return []
        # Chroma features at downsampled rate (still musical-meaningful).
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=2048)
        # Find boundaries via agglomerative segmentation
        bounds = librosa.segment.agglomerative(chroma, k=target_segments)
        bound_times = librosa.frames_to_time(bounds, sr=sr, hop_length=2048)
        if len(bound_times) < 2:
            return []
        # Build (start, end, mean_chroma) per segment.
        segments: list[tuple[float, float, np.ndarray]] = []
        end_time = float(len(y) / sr)
        for i in range(len(bound_times)):
            start = float(bound_times[i])
            end = float(bound_times[i + 1]) if i + 1 < len(bound_times) else end_time
            seg_chroma = chroma[
                :, bounds[i] : bounds[i + 1] if i + 1 < len(bounds) else chroma.shape[1]
            ]
            mean = seg_chroma.mean(axis=1) if seg_chroma.shape[1] > 0 else np.zeros(12)
            segments.append((start, end, mean))

        # Cluster segments by chroma similarity (cosine) into ~3 groups so
        # the labeller can distinguish chorus/verse/other.
        if len(segments) >= 3:
            from numpy.linalg import norm

            means = np.array([s[2] for s in segments])
            # Normalize, then cluster by argmax of similarity to centroids.
            normed = means / (norm(means, axis=1, keepdims=True) + 1e-9)
            # Three random "seed" centroids = first, middle, last segments
            seeds = normed[[0, len(normed) // 2, len(normed) - 1]]
            sims = normed @ seeds.T  # (n_segments, 3)
            labels = list(sims.argmax(axis=1))
        else:
            labels = list(range(len(segments)))

        sections: list[SongSection] = []
        for idx, ((start, end, _), lbl) in enumerate(zip(segments, labels)):
            sections.append(
                SongSection(
                    name=_label_section(idx, int(lbl), [int(x) for x in labels]),
                    start=start,
                    end=end,
                )
            )
        return sections
    except Exception as e:
        logger.warning("structure_detection failed for %s: %s", audio_path, e)
        return []
