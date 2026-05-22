"""
Transpose a chord progression by N semitones.
Vault ref: 03-LangChain-Core/04-Tools-Agents.md
"""
from __future__ import annotations

from langchain_core.tools import tool

_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def _split_chord(chord: str) -> tuple[str, str]:
    """Split 'Cmaj7' -> ('C', 'maj7'); 'F#m' -> ('F#', 'm')."""
    if len(chord) >= 2 and chord[1] in ("#", "b"):
        root, quality = chord[:2], chord[2:]
    else:
        root, quality = chord[:1], chord[1:]
    return _FLAT_TO_SHARP.get(root, root), quality


def transpose_chord(chord: str, semitones: int) -> str:
    root, quality = _split_chord(chord)
    if root not in _NOTES:
        return chord
    new_root = _NOTES[(_NOTES.index(root) + semitones) % 12]
    return f"{new_root}{quality}"


@tool
def transpose_progression(chords: list[str], semitones: int) -> list[str]:
    """Transpose a list of chords by the given number of semitones (positive = up)."""
    return [transpose_chord(c, semitones) for c in chords]
