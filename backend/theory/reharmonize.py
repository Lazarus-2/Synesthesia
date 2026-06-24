"""Deterministic reharmonization suggestions (Theory Lab).

Given a key and a chord (optionally the following chord), produce a list of
musically-valid substitution ideas — tritone subs, secondary dominants, modal
interchange, relative substitution, and diatonic-third substitution.

Everything here is **deterministic**: music21 supplies correct enharmonic
spelling and degree/function lookups; ``transpose_chord`` handles the pitch
arithmetic. No LLM, no randomness.

Public API
----------
reharmonize(key, chord, next_chord=None) -> list[dict]
    Each suggestion is ``{"type", "label", "chord", "explanation"}``.
"""

from __future__ import annotations

import re

from backend.theory.roman import _to_m21, smart_analyze
from backend.tools.chords import parse_chord
from backend.tools.transpose import _FLAT_TO_SHARP, transpose_chord

try:
    from music21 import key as m21_key_mod
    from music21 import roman as m21_roman
    from music21.harmony import chordSymbolFigureFromChord
    _MUSIC21_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MUSIC21_AVAILABLE = False

# Canonical qualities (from parse_chord) that act as DOMINANT sevenths.
# Explicitly excludes maj7, min7, m7b5, dim7 — those are not dominants.
_DOMINANT_QUALITIES = frozenset({"dom7", "9", "11", "13"})

# Canonical qualities that are "major-flavoured" for modal-interchange /
# relative-substitution purposes (i.e. built on a major third).
_MAJOR_QUALITIES = frozenset({"maj", "maj7", "maj9", "maj11", "maj13",
                              "dom7", "9", "11", "13", "6", "add9", "power"})
_MINOR_QUALITIES = frozenset({"min", "min7", "min9", "min11", "min13"})

_NO_CHORD = {"", "N", "NC", "N.C."}

# music21 flat spelling ('-') back to the 'b' convention used elsewhere.
_M21_FLAT_RE = re.compile(r"([A-G])-")


def _from_m21(label: str) -> str:
    """Render a music21 chord symbol ('B-7') back to the app convention ('Bb7')."""
    return _M21_FLAT_RE.sub(lambda m: m.group(1) + "b", label)


def _parse_key(key: str) -> tuple[str, str]:
    """Return ``(tonic, mode)`` from a key string like 'C major' / 'A minor'.

    Falls back to ``('C', 'major')`` for unparseable input.
    """
    m = re.match(r"^\s*([A-G][b#]?)\s+(major|minor)\s*$", key, re.IGNORECASE)
    if not m:
        # Bare tonic ("C", "Am" handled by callers) -> assume major.
        m2 = re.match(r"^\s*([A-G][b#]?)\s*$", key)
        if m2:
            return m2.group(1), "major"
        return "C", "major"
    return m.group(1), m.group(2).lower()


def _key_obj(key: str):
    tonic, mode = _parse_key(key)
    m21_tonic = tonic if mode == "major" else tonic.lower()
    return m21_key_mod.Key(_to_m21(m21_tonic), mode)


def _prefers_flats(key_obj) -> bool:
    """True if the key signature uses flats (negative ``sharps``)."""
    try:
        return bool(key_obj.sharps < 0)
    except Exception:  # pragma: no cover
        return False


def _respell_for_key(chord: str, key_obj) -> str:
    """Respell *chord*'s accidental to match the key's preferred accidental.

    ``transpose_chord`` always emits sharps (it normalises via ``_NOTES``).
    In a flat key we re-render the enharmonic equivalent with music21 so the
    suggestion reads idiomatically (e.g. Gb7 instead of F#7 in F major).
    """
    if not _MUSIC21_AVAILABLE:  # pragma: no cover
        return chord
    parts = parse_chord(chord)
    if not parts.root:
        return chord
    # Only sharps need consideration for flat-key respelling.
    if "#" not in parts.root or not _prefers_flats(key_obj):
        return chord
    # sharp -> flat enharmonic (e.g. F# -> Gb). Build via pitch class.
    sharp_to_flat = {v: k for k, v in _FLAT_TO_SHARP.items()}
    flat_root = sharp_to_flat.get(parts.root)
    if not flat_root:
        return chord
    return chord.replace(parts.root, flat_root, 1)


def _chord_root(chord: str) -> str | None:
    parts = parse_chord(chord)
    return parts.root or None


def reharmonize(key: str, chord: str, next_chord: str | None = None) -> list[dict]:
    """Return deterministic reharmonization suggestions for ``chord`` in ``key``.

    Each suggestion: ``{"type": str, "label": str, "chord": str, "explanation": str}``.
    Pure/deterministic (music21 for correct spelling). No LLM.
    """
    chord = (chord or "").strip()
    if chord.upper() in {c.upper() for c in _NO_CHORD}:
        return []

    parts = parse_chord(chord)
    if not parts.root:
        return []

    suggestions: list[dict] = []
    key_obj = _key_obj(key) if _MUSIC21_AVAILABLE else None
    root, quality = parts.root, parts.quality

    # --- tritone_sub: only for dominant sevenths -------------------------
    if quality in _DOMINANT_QUALITIES:
        sub = transpose_chord(f"{root}7", 6)  # dominant a tritone away
        sub = _respell_for_key(sub, key_obj) if key_obj is not None else sub
        suggestions.append({
            "type": "tritone_sub",
            "label": "Tritone substitution",
            "chord": sub,
            "explanation": "Shares the 3rd & 7th; gives a chromatic bass descent.",
        })

    # --- secondary_dominant: V7 of the next chord ------------------------
    if next_chord and next_chord.strip().upper() not in {c.upper() for c in _NO_CHORD}:
        next_root = _chord_root(next_chord.strip())
        if next_root:
            # Dominant a perfect 5th above the next chord's root.
            sec = transpose_chord(f"{next_root}7", 7)
            sec = _respell_for_key(sec, key_obj) if key_obj is not None else sec
            suggestions.append({
                "type": "secondary_dominant",
                "label": "Secondary dominant (V7/next)",
                "chord": sec,
                "explanation": "Tonicizes the next chord.",
            })

    # --- modal_interchange: parallel-mode counterpart --------------------
    if quality in _MAJOR_QUALITIES:
        suggestions.append({
            "type": "modal_interchange",
            "label": "Modal interchange (borrowed)",
            "chord": f"{root}m",
            "explanation": "Borrowed from the parallel mode.",
        })
    elif quality in _MINOR_QUALITIES:
        suggestions.append({
            "type": "modal_interchange",
            "label": "Modal interchange (borrowed)",
            "chord": root,
            "explanation": "Borrowed from the parallel mode.",
        })

    # --- relative_sub: relative minor/major ------------------------------
    if quality in _MAJOR_QUALITIES:
        rel = transpose_chord(f"{root}m", -3)  # relative minor (down a m3)
        rel = _respell_for_key(rel, key_obj) if key_obj is not None else rel
        suggestions.append({
            "type": "relative_sub",
            "label": "Relative substitution",
            "chord": rel,
            "explanation": "Relative key — shares two chord tones.",
        })
    elif quality in _MINOR_QUALITIES:
        rel = transpose_chord(root, 3)  # relative major (up a m3)
        rel = _respell_for_key(rel, key_obj) if key_obj is not None else rel
        suggestions.append({
            "type": "relative_sub",
            "label": "Relative substitution",
            "chord": rel,
            "explanation": "Relative key — shares two chord tones.",
        })

    # --- diatonic_third: diatonic chord a third above --------------------
    if _MUSIC21_AVAILABLE and key_obj is not None:
        third = _diatonic_third(chord, key_obj)
        if third is not None:
            suggestions.append({
                "type": "diatonic_third",
                "label": "Diatonic third substitution",
                "chord": third,
                "explanation": "Diatonic chord a third away; shares two tones.",
            })

    return suggestions


def _diatonic_third(chord: str, key_obj) -> str | None:
    """Return the diatonic triad a third above *chord*'s degree, or None.

    Uses ``smart_analyze`` to find the chord's scale degree; if the chord
    isn't diatonic (None, secondary, or has a leading accidental on the
    figure) the substitution is skipped.
    """
    try:
        rn = smart_analyze(chord, key_obj)
    except Exception:
        return None
    if rn is None:
        return None
    # Skip secondary dominants and accidental-prefixed (borrowed/chromatic) chords.
    if getattr(rn, "secondaryRomanNumeral", None) is not None:
        return None
    figure = getattr(rn, "primaryFigure", "") or ""
    if figure[:1] in ("b", "#"):
        return None
    deg = getattr(rn, "scaleDegree", None)
    if not deg:
        return None
    # Degree a third above (wrap within 1..7).
    target = ((deg + 2 - 1) % 7) + 1
    try:
        rn_target = m21_roman.RomanNumeral(target, key_obj)
        figure = chordSymbolFigureFromChord(rn_target)
    except Exception:
        return None
    if not figure or figure in ("Chord Symbol Cannot Be Identified",):
        return None
    return _from_m21(figure)
