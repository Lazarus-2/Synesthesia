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
# Every quality that parse_chord can emit must have an explicit entry here so
# that transpose_chord produces a recognisable chord symbol. Do NOT rely on the
# raw-quality fallback (suffix = parts.quality) for user-visible output.
_QUALITY_SUFFIX = {
    # major family
    "maj": "",
    "maj7": "maj7",
    "maj9": "maj9",
    "maj11": "maj11",
    "maj13": "maj13",
    # minor family
    "min": "m",
    "min7": "m7",
    "min9": "m9",
    "min11": "m11",
    "min13": "m13",
    # dominant / plain extensions
    "dom7": "7",
    "9": "9",
    "11": "11",
    "13": "13",
    "6": "6",
    # half-diminished / diminished
    "m7b5": "m7b5",
    "dim": "dim",
    "dim7": "dim7",
    # augmented
    "aug": "aug",
    # suspended / added
    "sus2": "sus2",
    "sus4": "sus4",
    "add9": "add9",
    # power chord
    "power": "5",
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
