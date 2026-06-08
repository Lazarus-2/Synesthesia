"""
Canonical chord-symbol parser. ONE source of truth for root / quality / bass so
no consumer (voicings, transpose, capo, synesthesia_colors) re-invents fragile
substring checks like ``"m" in suffix`` (which mis-catches ``maj7``).

Vault ref: 03-LangChain-Core/04-Tools-Agents.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Leading-token -> canonical quality. ORDER MATTERS: longer / more specific
# tokens must be tested before their prefixes (e.g. "maj7" before "maj",
# "m7b5" before "m7" before "m", "dim7" before "dim").
_QUALITY_RULES: list[tuple[str, str]] = [
    ("maj7", "maj7"),
    ("maj9", "maj9"),
    ("M7", "maj7"),
    ("m7b5", "m7b5"),
    ("min7b5", "m7b5"),
    ("dim7", "dim7"),
    ("dim", "dim"),
    ("aug", "aug"),
    ("sus2", "sus2"),
    ("sus4", "sus4"),
    ("sus", "sus4"),
    ("add9", "add9"),
    ("min7", "min7"),
    ("m7", "min7"),
    ("min", "min"),
    ("maj", "maj"),
    ("13", "13"),
    ("11", "11"),
    ("9", "9"),
    ("7", "dom7"),
    ("6", "6"),
    ("ø", "m7b5"),
    ("o", "dim"),
    ("+", "aug"),
    ("m", "min"),
    ("", "maj"),
]

_ROOT_RE = re.compile(r"^([A-Ga-g][b#]?)")


@dataclass(frozen=True)
class ChordParts:
    root: str
    quality: str
    bass: str | None


def _norm_root(token: str) -> str:
    """Capitalize the letter, keep the accidental lowercase-b / sharp as-is."""
    if not token:
        return ""
    return token[0].upper() + token[1:]


def parse_chord(label: str) -> ChordParts:
    """Parse a chord label into (root incl. accidental, canonical quality, slash bass).

    ``parse_chord('Cmaj7').quality == 'maj7'`` (NOT 'min').
    ``parse_chord('Dm7/G') == ChordParts('D', 'min7', 'G')``.
    Unknown / no-chord labels yield an empty root.
    """
    label = (label or "").strip()
    if not label or label.upper() in ("N", "N.C.", "NC"):
        return ChordParts(root="", quality="maj", bass=None)

    # Split off slash bass first so the suffix scanner never sees it.
    bass: str | None = None
    if "/" in label:
        head, _, tail = label.partition("/")
        label = head
        m_bass = _ROOT_RE.match(tail.strip())
        bass = _norm_root(m_bass.group(1)) if m_bass else None

    m_root = _ROOT_RE.match(label)
    if not m_root:
        return ChordParts(root="", quality="maj", bass=bass)

    root = _norm_root(m_root.group(1))
    suffix = label[m_root.end():]

    quality = "maj"
    for token, canonical in _QUALITY_RULES:
        if suffix.startswith(token):
            quality = canonical
            break

    return ChordParts(root=root, quality=quality, bass=bass)
