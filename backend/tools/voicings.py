"""
Chord-diagram lookup. Deterministic (NOT LLM-generated) -- we load shapes from
a curated DB and return them as structured data.

Vault ref: 03-LangChain-Core/04-Tools-Agents.md
"""
from __future__ import annotations

from backend.schemas import ChordDiagram, Instrument

# Minimal seed DB. TODO(Module 3, Lesson 4): expand or import chords-db.
_GUITAR_SHAPES: dict[str, dict] = {
    "C":   {"frets": [-1, 3, 2, 0, 1, 0], "fingers": [0, 3, 2, 0, 1, 0]},
    "G":   {"frets": [3, 2, 0, 0, 0, 3],  "fingers": [3, 2, 0, 0, 0, 4]},
    "D":   {"frets": [-1, -1, 0, 2, 3, 2], "fingers": [0, 0, 0, 1, 3, 2]},
    "Em":  {"frets": [0, 2, 2, 0, 0, 0],  "fingers": [0, 2, 3, 0, 0, 0]},
    "Am":  {"frets": [-1, 0, 2, 2, 1, 0], "fingers": [0, 0, 2, 3, 1, 0]},
    "E":   {"frets": [0, 2, 2, 1, 0, 0],  "fingers": [0, 2, 3, 1, 0, 0]},
    "A":   {"frets": [-1, 0, 2, 2, 2, 0], "fingers": [0, 0, 1, 2, 3, 0]},
    "F":   {"frets": [1, 3, 3, 2, 1, 1],  "fingers": [1, 3, 4, 2, 1, 1]},
    "Dm":  {"frets": [-1, -1, 0, 2, 3, 1], "fingers": [0, 0, 0, 2, 3, 1]},
}

_PIANO_TRIADS: dict[str, dict] = {
    "C":  {"right_hand": ["C4", "E4", "G4"],  "left_hand": ["C3"]},
    "G":  {"right_hand": ["G4", "B4", "D5"],  "left_hand": ["G2"]},
    "D":  {"right_hand": ["D4", "F#4", "A4"], "left_hand": ["D3"]},
    "Em": {"right_hand": ["E4", "G4", "B4"],  "left_hand": ["E3"]},
    "Am": {"right_hand": ["A3", "C4", "E4"],  "left_hand": ["A2"]},
    "F":  {"right_hand": ["F4", "A4", "C5"],  "left_hand": ["F2"]},
    "Dm": {"right_hand": ["D4", "F4", "A4"],  "left_hand": ["D3"]},
}


def get_chord_diagrams(
    chords: list[str],
    instrument: Instrument = "guitar",
) -> list[ChordDiagram]:
    """Return ChordDiagram for each unique chord in the progression."""
    unique = list(dict.fromkeys(chords))
    diagrams: list[ChordDiagram] = []

    if instrument == "guitar":
        for c in unique:
            shape = _GUITAR_SHAPES.get(c)
            if shape:
                diagrams.append(ChordDiagram(chord=c, instrument="guitar", **shape))
    elif instrument == "piano":
        for c in unique:
            notes = _PIANO_TRIADS.get(c)
            if notes:
                diagrams.append(ChordDiagram(chord=c, instrument="piano", **notes))
    # TODO(Module 3, Lesson 4): add ukulele, bass, and handle extensions (7ths, sus, etc.)
    return diagrams
