"""
Suggest a capo position that turns tricky chords into easy open-string chords.
Vault ref: 03-LangChain-Core/04-Tools-Agents.md
"""
from __future__ import annotations

from langchain_core.tools import tool

from backend.tools.transpose import transpose_chord

# Chords playable as open-string shapes on guitar
EASY_OPEN = {"C", "D", "E", "G", "A", "Am", "Em", "Dm", "D7", "E7", "A7", "G7", "C7"}


@tool
def suggest_capo(chords: list[str]) -> dict:
    """Find capo fret (0-7) that maximizes number of easy open-shape chords.

    Returns {"capo": int, "shapes": list[str], "score": int}.
    """
    best = {"capo": 0, "shapes": chords, "score": sum(c in EASY_OPEN for c in chords)}
    for fret in range(1, 8):
        # capo on fret N means chord at fret N sounds as-written, so the shape is N semitones LOWER
        shapes = [transpose_chord(c, -fret) for c in chords]
        score = sum(s in EASY_OPEN for s in shapes)
        if score > best["score"]:
            best = {"capo": fret, "shapes": shapes, "score": score}
    return best
