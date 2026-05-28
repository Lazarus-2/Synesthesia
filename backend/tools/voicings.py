"""
Chord-diagram lookup. Deterministic (NOT LLM-generated) -- we load shapes from
a curated DB and return them as structured data.

Vault ref: 03-LangChain-Core/04-Tools-Agents.md
"""
from __future__ import annotations

from backend.schemas import ChordDiagram, Instrument

_GUITAR_SHAPES: dict[str, dict] = {
    "C":   {"frets": [-1, 3, 2, 0, 1, 0], "fingers": [0, 3, 2, 0, 1, 0]},
    "Cmaj7": {"frets": [-1, 3, 2, 0, 0, 0], "fingers": [0, 3, 2, 0, 0, 0]},
    "C7":  {"frets": [-1, 3, 2, 3, 1, 0], "fingers": [0, 3, 2, 4, 1, 0]},
    "G":   {"frets": [3, 2, 0, 0, 0, 3],  "fingers": [3, 2, 0, 0, 0, 4]},
    "G7":  {"frets": [3, 2, 0, 0, 0, 1],  "fingers": [3, 2, 0, 0, 0, 1]},
    "D":   {"frets": [-1, -1, 0, 2, 3, 2], "fingers": [0, 0, 0, 1, 3, 2]},
    "Dm7": {"frets": [-1, -1, 0, 2, 1, 1], "fingers": [0, 0, 0, 2, 1, 1]},
    "D7":  {"frets": [-1, -1, 0, 2, 1, 2], "fingers": [0, 0, 0, 2, 1, 3]},
    "Em":  {"frets": [0, 2, 2, 0, 0, 0],  "fingers": [0, 2, 3, 0, 0, 0]},
    "Em7": {"frets": [0, 2, 2, 0, 3, 0],  "fingers": [0, 2, 3, 0, 4, 0]},
    "Am":  {"frets": [-1, 0, 2, 2, 1, 0], "fingers": [0, 0, 2, 3, 1, 0]},
    "Am7": {"frets": [-1, 0, 2, 0, 1, 0], "fingers": [0, 0, 2, 0, 1, 0]},
    "E":   {"frets": [0, 2, 2, 1, 0, 0],  "fingers": [0, 2, 3, 1, 0, 0]},
    "E7":  {"frets": [0, 2, 0, 1, 0, 0],  "fingers": [0, 2, 0, 1, 0, 0]},
    "A":   {"frets": [-1, 0, 2, 2, 2, 0], "fingers": [0, 0, 1, 2, 3, 0]},
    "A7":  {"frets": [-1, 0, 2, 0, 2, 0], "fingers": [0, 0, 2, 0, 3, 0]},
    "F":   {"frets": [1, 3, 3, 2, 1, 1],  "fingers": [1, 3, 4, 2, 1, 1]},
    "Fmaj7": {"frets": [-1, -1, 3, 2, 1, 0], "fingers": [0, 0, 3, 2, 1, 0]},
    "Dm":  {"frets": [-1, -1, 0, 2, 3, 1], "fingers": [0, 0, 0, 2, 3, 1]},
}

_UKULELE_SHAPES: dict[str, dict] = {
    "C":   {"frets": [0, 0, 0, 3], "fingers": [0, 0, 0, 3]},
    "G":   {"frets": [0, 2, 3, 2], "fingers": [0, 1, 3, 2]},
    "D":   {"frets": [2, 2, 2, 0], "fingers": [1, 2, 3, 0]},
    "Em":  {"frets": [0, 4, 3, 2], "fingers": [0, 3, 2, 1]},
    "Am":  {"frets": [2, 0, 0, 0], "fingers": [2, 0, 0, 0]},
    "F":   {"frets": [2, 0, 1, 0], "fingers": [2, 0, 1, 0]},
    "Dm":  {"frets": [2, 2, 1, 0], "fingers": [2, 3, 1, 0]},
}

_BASS_SHAPES: dict[str, dict] = {
    "C":   {"frets": [-1, 3, -1, -1], "fingers": [0, 3, 0, 0]},
    "G":   {"frets": [3, -1, -1, -1], "fingers": [3, 0, 0, 0]},
    "D":   {"frets": [-1, -1, 0, -1], "fingers": [0, 0, 0, 0]},
    "Em":  {"frets": [0, -1, -1, -1], "fingers": [0, 0, 0, 0]},
    "Am":  {"frets": [-1, 0, -1, -1], "fingers": [0, 0, 0, 0]},
    "F":   {"frets": [1, -1, -1, -1], "fingers": [1, 0, 0, 0]},
    "Dm":  {"frets": [-1, -1, 0, -1], "fingers": [0, 0, 0, 0]},
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

    for c in unique:
        # Simplify complex extensions if not found
        base_chord = c
        if c not in _GUITAR_SHAPES and c not in _PIANO_TRIADS:
            # Fallback to major or minor
            base_chord = c.replace("maj7", "").replace("m7", "m").replace("7", "").replace("sus4", "")

        if instrument == "guitar":
            shape = _GUITAR_SHAPES.get(base_chord, _GUITAR_SHAPES.get(c))
            if shape:
                diagrams.append(ChordDiagram(chord=c, instrument="guitar", **shape))
        elif instrument == "piano":
            notes = _PIANO_TRIADS.get(base_chord, _PIANO_TRIADS.get(c))
            if notes:
                diagrams.append(ChordDiagram(chord=c, instrument="piano", **notes))
        elif instrument == "ukulele":
            shape = _UKULELE_SHAPES.get(base_chord, _UKULELE_SHAPES.get(c))
            if shape:
                diagrams.append(ChordDiagram(chord=c, instrument="ukulele", **shape))
        elif instrument == "bass":
            shape = _BASS_SHAPES.get(base_chord, _BASS_SHAPES.get(c))
            if shape:
                diagrams.append(ChordDiagram(chord=c, instrument="bass", **shape))

    return diagrams
