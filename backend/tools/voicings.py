"""
Chord-diagram lookup. Deterministic (NOT LLM-generated) -- we load shapes from
a curated DB and return them as structured data.

Vault ref: 03-LangChain-Core/04-Tools-Agents.md
"""

from __future__ import annotations

from backend.schemas import ChordDiagram, Instrument
from backend.tools.chords import parse_chord

_GUITAR_SHAPES: dict[str, dict] = {
    "C": {"frets": [-1, 3, 2, 0, 1, 0], "fingers": [0, 3, 2, 0, 1, 0]},
    "Cmaj7": {"frets": [-1, 3, 2, 0, 0, 0], "fingers": [0, 3, 2, 0, 0, 0]},
    "C7": {"frets": [-1, 3, 2, 3, 1, 0], "fingers": [0, 3, 2, 4, 1, 0]},
    "G": {"frets": [3, 2, 0, 0, 0, 3], "fingers": [3, 2, 0, 0, 0, 4]},
    "G7": {"frets": [3, 2, 0, 0, 0, 1], "fingers": [3, 2, 0, 0, 0, 1]},
    "D": {"frets": [-1, -1, 0, 2, 3, 2], "fingers": [0, 0, 0, 1, 3, 2]},
    "Dm7": {"frets": [-1, -1, 0, 2, 1, 1], "fingers": [0, 0, 0, 2, 1, 1]},
    "D7": {"frets": [-1, -1, 0, 2, 1, 2], "fingers": [0, 0, 0, 2, 1, 3]},
    "Em": {"frets": [0, 2, 2, 0, 0, 0], "fingers": [0, 2, 3, 0, 0, 0]},
    "Em7": {"frets": [0, 2, 2, 0, 3, 0], "fingers": [0, 2, 3, 0, 4, 0]},
    "Am": {"frets": [-1, 0, 2, 2, 1, 0], "fingers": [0, 0, 2, 3, 1, 0]},
    "Am7": {"frets": [-1, 0, 2, 0, 1, 0], "fingers": [0, 0, 2, 0, 1, 0]},
    "E": {"frets": [0, 2, 2, 1, 0, 0], "fingers": [0, 2, 3, 1, 0, 0]},
    "E7": {"frets": [0, 2, 0, 1, 0, 0], "fingers": [0, 2, 0, 1, 0, 0]},
    "A": {"frets": [-1, 0, 2, 2, 2, 0], "fingers": [0, 0, 1, 2, 3, 0]},
    "A7": {"frets": [-1, 0, 2, 0, 2, 0], "fingers": [0, 0, 2, 0, 3, 0]},
    "F": {"frets": [1, 3, 3, 2, 1, 1], "fingers": [1, 3, 4, 2, 1, 1]},
    "Fmaj7": {"frets": [-1, -1, 3, 2, 1, 0], "fingers": [0, 0, 3, 2, 1, 0]},
    "Dm": {"frets": [-1, -1, 0, 2, 3, 1], "fingers": [0, 0, 0, 2, 3, 1]},
}

_UKULELE_SHAPES: dict[str, dict] = {
    "C": {"frets": [0, 0, 0, 3], "fingers": [0, 0, 0, 3]},
    "G": {"frets": [0, 2, 3, 2], "fingers": [0, 1, 3, 2]},
    "D": {"frets": [2, 2, 2, 0], "fingers": [1, 2, 3, 0]},
    "Em": {"frets": [0, 4, 3, 2], "fingers": [0, 3, 2, 1]},
    "Am": {"frets": [2, 0, 0, 0], "fingers": [2, 0, 0, 0]},
    "F": {"frets": [2, 0, 1, 0], "fingers": [2, 0, 1, 0]},
    "Dm": {"frets": [2, 2, 1, 0], "fingers": [2, 3, 1, 0]},
}

_BASS_SHAPES: dict[str, dict] = {
    "C": {"frets": [-1, 3, -1, -1], "fingers": [0, 3, 0, 0]},
    "G": {"frets": [3, -1, -1, -1], "fingers": [3, 0, 0, 0]},
    "D": {"frets": [-1, -1, 0, -1], "fingers": [0, 0, 0, 0]},
    "Em": {"frets": [0, -1, -1, -1], "fingers": [0, 0, 0, 0]},
    "Am": {"frets": [-1, 0, -1, -1], "fingers": [0, 0, 0, 0]},
    "F": {"frets": [1, -1, -1, -1], "fingers": [1, 0, 0, 0]},
    "Dm": {"frets": [-1, -1, 0, -1], "fingers": [0, 0, 0, 0]},
}

_PIANO_TRIADS: dict[str, dict] = {
    "C": {"right_hand": ["C4", "E4", "G4"], "left_hand": ["C3"]},
    "G": {"right_hand": ["G4", "B4", "D5"], "left_hand": ["G2"]},
    "D": {"right_hand": ["D4", "F#4", "A4"], "left_hand": ["D3"]},
    "Em": {"right_hand": ["E4", "G4", "B4"], "left_hand": ["E3"]},
    "Am": {"right_hand": ["A3", "C4", "E4"], "left_hand": ["A2"]},
    "F": {"right_hand": ["F4", "A4", "C5"], "left_hand": ["F2"]},
    "Dm": {"right_hand": ["D4", "F4", "A4"], "left_hand": ["D3"]},
}


# Canonical quality -> the simplest label we keep a shape for. Used only as a
# *degradation* target so an extended/unknown chord still yields a diagram
# instead of being silently dropped.
_DEGRADE_SUFFIX = {
    "maj": "",
    "maj7": "maj7",
    "dom7": "7",
    "min": "m",
    "min7": "m7",
    "m7b5": "m",
    "dim": "m",
    "aug": "",
    "sus2": "",
    "sus4": "",
    "6": "",
    "9": "",
    "11": "",
    "13": "",
    "add9": "",
    "maj9": "maj7",
    "min9": "m",
}


def _candidate_labels(label: str) -> list[str]:
    """Ordered lookup keys for a chord: exact, then degraded toward a triad."""
    parts = parse_chord(label)
    if not parts.root:
        return [label]
    candidates = [label]  # try the exact label first (e.g. "Cmaj7", "Am7")
    suffix = _DEGRADE_SUFFIX.get(parts.quality, "")
    candidates.append(f"{parts.root}{suffix}")  # degraded (e.g. "Am" for "Am9")
    candidates.append(parts.root)  # last resort: bare triad ("D" for "D/F#")
    return candidates


def get_chord_diagrams(
    chords: list[str],
    instrument: Instrument = "guitar",
) -> list[ChordDiagram]:
    """Return a ChordDiagram for each unique chord in the progression.

    Extended/unknown chords degrade to their triad shape via ``parse_chord``
    rather than being silently dropped — only truly unparseable labels (no
    recognizable root) and roots with no table entry are skipped.
    """
    unique = list(dict.fromkeys(chords))
    diagrams: list[ChordDiagram] = []

    table = {
        "guitar": _GUITAR_SHAPES,
        "piano": _PIANO_TRIADS,
        "ukulele": _UKULELE_SHAPES,
        "bass": _BASS_SHAPES,
    }[instrument]

    for c in unique:
        shape = None
        for key in _candidate_labels(c):
            shape = table.get(key)
            if shape:
                break
        if shape:
            # Preserve the ORIGINAL label on the diagram even when we fell back
            # to a degraded shape, so the UI still says "Am7".
            diagrams.append(ChordDiagram(chord=c, instrument=instrument, **shape))

    return diagrams
