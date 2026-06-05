"""
'Similar songs' chain using chord-progression embeddings.
Vault refs:
  - 02-LLM-Architecture/02-RAG-Architecture.md
  - 03-LangChain-Core/03-Retrieval-Chains.md
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)


_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_NOTE_TO_IDX = {n: i for i, n in enumerate(_NOTES)}
_FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def _parse_root_quality(chord: str) -> tuple[str | None, bool, bool]:
    """Return (normalized_root, is_minor, is_seventh) for a chord symbol."""
    if not chord or chord == "N.C.":
        return None, False, False
    root = chord[0]
    suffix_start = 1
    if len(chord) > 1 and chord[1] in ("#", "b"):
        if chord[1] == "b":
            root = _FLATS.get(chord[:2], chord[0])
        else:
            root = chord[:2]
        suffix_start = 2
    suffix = chord[suffix_start:].lower()
    is_minor = ("m" in suffix and "maj" not in suffix) or suffix.startswith("min")
    is_seventh = "7" in suffix
    if root not in _NOTE_TO_IDX:
        return None, False, False
    return root, is_minor, is_seventh


def embed_progression(chords: list[str]) -> list[float]:
    """Embed a chord sequence as a 12-D pitch-class vector (chromagram).

    Bag-of-pitch-classes. Cheap, deterministic, and invariant under chord
    reordering — which is the wrong invariant for "songs that *sound* like
    each other." Use :func:`embed_progression_v2` for sequence-aware
    similarity that beats this in side-by-side eval.
    """
    vec = [0.0] * 12
    if not chords:
        return vec

    for chord in chords:
        root, is_minor, _ = _parse_root_quality(chord)
        if root is None:
            continue
        idx = _NOTE_TO_IDX[root]
        vec[idx] += 1.0  # Root weight
        if is_minor:
            vec[(idx + 3) % 12] += 0.5
        else:
            vec[(idx + 4) % 12] += 0.5
        vec[(idx + 7) % 12] += 0.5

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def embed_progression_v2(
    chords: list[str],
    key: str | None = None,
) -> list[float]:
    """Sequence- and key-aware progression embedding (Plan 3 A6).

    Improvements over :func:`embed_progression`:
    1. **Sequence-aware** — adjacent-pair pitch-class deltas captured in a
       12-D transition vector. Two songs that use the same chords but in
       very different orders no longer score 1.0.
    2. **Key-conditional** — when ``key`` is provided we rotate everything
       to ``C`` (or ``A`` for minor) so I-V-vi-IV in *any* key matches
       I-V-vi-IV in any other key.
    3. **Seventh + minor flags** — separate counters preserve quality
       information that the chromagram blurs.

    Returns a 36-D vector: ``[ pitch_class_12, transition_12, qualities_12 ]``
    laid out so cosine similarity is well-defined.
    """
    pc = [0.0] * 12  # pitch-class counts (rotated)
    transitions = [0.0] * 12  # interval-from-previous-root (rotated)
    qualities = [0.0] * 12  # quality features: minor/seventh by root class

    if not chords:
        return pc + transitions + qualities

    # Resolve key rotation: how many semitones to shift down so the tonic
    # lands on C. If the key is missing or unrecognised, no rotation.
    key_offset = 0
    if key:
        key_root = key.strip().split()[0]
        key_root_norm = _FLATS.get(
            key_root,
            key_root.replace("b", "") if len(key_root) > 1 and key_root[1] == "b" else key_root,
        )
        if key_root_norm in _NOTE_TO_IDX:
            key_offset = _NOTE_TO_IDX[key_root_norm]

    prev_idx: int | None = None
    for chord in chords:
        root, is_minor, is_seventh = _parse_root_quality(chord)
        if root is None:
            prev_idx = None
            continue
        raw_idx = _NOTE_TO_IDX[root]
        idx = (raw_idx - key_offset) % 12
        pc[idx] += 1.0
        if is_minor:
            pc[(idx + 3) % 12] += 0.5
            qualities[idx] += 0.7  # minor-quality marker on the rotated root
        else:
            pc[(idx + 4) % 12] += 0.5
        pc[(idx + 7) % 12] += 0.5
        if is_seventh:
            qualities[(idx + 10) % 12] += 0.5  # 7th adds a "minor-7th" bin

        if prev_idx is not None:
            delta = (idx - prev_idx) % 12
            transitions[delta] += 1.0
        prev_idx = idx

    # L2-normalize each segment independently so equal-weighted cosine
    # similarity isn't dominated by whichever segment had more events.
    def _normalize(seg: list[float]) -> list[float]:
        n = math.sqrt(sum(x * x for x in seg))
        return [x / n for x in seg] if n > 0 else seg

    return _normalize(pc) + _normalize(transitions) + _normalize(qualities)


# Module-level cache of seed songs (re-read every call previously).
_GOLDEN_SONGS: list[dict] | None = None
_DEFAULT_SEED_SONGS: list[dict] = [
    {"title": "Let It Be", "artist": "The Beatles", "expected_progression": ["C", "G", "Am", "F"]},
    {
        "title": "Wonderwall",
        "artist": "Oasis",
        "expected_progression": ["Em7", "G", "Dsus4", "A7sus4"],
    },
    {
        "title": "Autumn Leaves",
        "artist": "Various",
        "expected_progression": ["Cm7", "F7", "BbMaj7", "EbMaj7"],
    },
]


def _load_golden_songs() -> list[dict]:
    """Load the seed song catalog once and cache it."""
    global _GOLDEN_SONGS
    if _GOLDEN_SONGS is not None:
        return _GOLDEN_SONGS

    # backend/chains/similarity_chain.py → backend/ → backend/tests/golden_songs.json
    golden_path = Path(__file__).parent.parent / "tests" / "golden_songs.json"
    if golden_path.exists():
        try:
            with golden_path.open("r") as f:
                data = json.load(f)
                songs = data.get("songs", [])
                if songs:
                    _GOLDEN_SONGS = songs
                    return _GOLDEN_SONGS
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read golden_songs.json: %s", e)

    _GOLDEN_SONGS = list(_DEFAULT_SEED_SONGS)
    return _GOLDEN_SONGS


def find_similar(
    chords: list[str],
    k: int = 5,
    key: str | None = None,
) -> list[dict]:
    """Return top-k similar songs using the v2 sequence-aware embedding.

    Falls back to set-based Jaccard if a numpy / linalg error fires (which
    shouldn't happen for any deterministic chord input — it's a defensive
    net rather than an expected path).
    """
    import numpy as np

    songs = _load_golden_songs()
    results: list[dict] = []

    try:
        query_vec = np.array(embed_progression_v2(chords, key=key))

        for s in songs:
            prog = s.get("expected_progression", [])
            if not prog:
                continue
            cand_key = s.get("key")  # honour per-song key if the seed lists one
            cand_vec = np.array(embed_progression_v2(prog, key=cand_key))
            dot = float(np.dot(query_vec, cand_vec))
            nq = float(np.linalg.norm(query_vec))
            nc = float(np.linalg.norm(cand_vec))
            score = (dot / (nq * nc)) if (nq > 0 and nc > 0) else 0.0
            results.append(
                {
                    "title": s.get("title", "Unknown"),
                    "artist": s.get("artist", "Unknown"),
                    "progression": prog,
                    "score": float(score),
                }
            )
    except (ValueError, np.linalg.LinAlgError) as e:
        logger.warning("Sequence-aware similarity failed; falling back to Jaccard: %s", e)
        query_set = set(chords)
        results.clear()
        for s in songs:
            prog = s.get("expected_progression", [])
            if not prog:
                continue
            cand_set = set(prog)
            inter = query_set.intersection(cand_set)
            union = query_set.union(cand_set)
            score = float(len(inter) / len(union)) if union else 0.0
            results.append(
                {
                    "title": s.get("title", "Unknown"),
                    "artist": s.get("artist", "Unknown"),
                    "progression": prog,
                    "score": score,
                }
            )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:k]
