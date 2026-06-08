"""
Suggest a capo position that turns tricky chords into easy open-string chords.
Vault ref: 03-LangChain-Core/04-Tools-Agents.md
"""

from __future__ import annotations

from langchain_core.tools import tool

from backend.tools.chords import parse_chord
from backend.tools.transpose import transpose_chord

# Open-string-playable shapes on guitar, expressed as (root, quality) so a
# label like "Em7" or "G/B" is judged on its parsed identity, not a raw string.
_EASY_OPEN_PARTS = {
    ("C", "maj"), ("D", "maj"), ("E", "maj"), ("G", "maj"), ("A", "maj"),
    ("A", "min"), ("E", "min"), ("D", "min"),
    ("D", "dom7"), ("E", "dom7"), ("A", "dom7"), ("G", "dom7"), ("C", "dom7"),
}


def _is_easy_open(chord: str) -> bool:
    """True when the chord's parsed (root, quality) is an open-string shape."""
    parts = parse_chord(chord)
    if not parts.root:
        return False
    return (parts.root, parts.quality) in _EASY_OPEN_PARTS


@tool
def suggest_capo(chords: list[str]) -> dict:
    """Find capo fret (0-7) that maximizes number of easy open-shape chords.

    Returns {"capo": int, "shapes": list[str], "score": int}.
    """
    best = {"capo": 0, "shapes": chords, "score": sum(_is_easy_open(c) for c in chords)}
    for fret in range(1, 8):
        # capo on fret N means chord at fret N sounds as-written, so the shape is N semitones LOWER
        shapes = [transpose_chord(c, -fret) for c in chords]
        score = sum(_is_easy_open(s) for s in shapes)
        if score > best["score"]:
            best = {"capo": fret, "shapes": shapes, "score": score}
    return best
