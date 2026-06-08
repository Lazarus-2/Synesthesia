"""
Transpose a chord progression by N semitones.
Vault ref: 03-LangChain-Core/04-Tools-Agents.md
"""

from __future__ import annotations

from langchain_core.tools import tool

from backend.tools.chords import parse_chord

_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

# Canonical quality -> printable suffix (inverse of parse_chord's normalization).
_QUALITY_SUFFIX = {
    "maj": "",
    "min": "m",
    "dom7": "7",
    "maj7": "maj7",
    "maj9": "maj9",
    "min7": "m7",
    "m7b5": "m7b5",
    "dim": "dim",
    "dim7": "dim7",
    "aug": "aug",
    "sus2": "sus2",
    "sus4": "sus4",
    "add9": "add9",
    "6": "6",
    "9": "9",
    "11": "11",
    "13": "13",
}


def _shift_note(note: str, semitones: int) -> str | None:
    """Transpose a single note name; return None if it isn't a recognized note."""
    note = _FLAT_TO_SHARP.get(note, note)
    if note not in _NOTES:
        return None
    return _NOTES[(_NOTES.index(note) + semitones) % 12]


def transpose_chord(chord: str, semitones: int) -> str:
    parts = parse_chord(chord)
    if not parts.root:
        return chord  # N.C. / unparseable -> passthrough

    new_root = _shift_note(parts.root, semitones)
    if new_root is None:
        return chord

    suffix = _QUALITY_SUFFIX.get(parts.quality, parts.quality)
    out = f"{new_root}{suffix}"

    if parts.bass:
        new_bass = _shift_note(parts.bass, semitones)
        out = f"{out}/{new_bass}" if new_bass else out
    return out


@tool
def transpose_progression(chords: list[str], semitones: int) -> list[str]:
    """Transpose a list of chords by the given number of semitones (positive = up)."""
    return [transpose_chord(c, semitones) for c in chords]
