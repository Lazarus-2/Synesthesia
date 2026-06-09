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


# Canonical quality -> the suffix for the DEGRADED fallback shape.
#
# Degradation policy (applied when the exact chord label is not in the table):
#   - major-family (maj, maj7, maj9, maj11, maj13, dom7, 6, 9, 11, 13, sus*, add9,
#     aug, power): degrade to the bare major triad ("").
#   - minor-family (min, min7, min9, min11, min13): degrade to the minor triad ("m").
#   - dim7 / m7b5 / dim: these are tonally DISTINCT from major/minor triads.
#     Showing an Am shape for "Adim" would be musically WRONG and mislead the
#     player. We therefore map them to None (sentinel) so _candidate_labels
#     returns only the exact label — if the table has no dim shape, the chord
#     is DROPPED (no diagram) rather than shown with an incorrect shape.
_DEGRADE_SUFFIX: dict[str, str | None] = {
    # major triad family
    "maj": "",
    "maj7": "",
    "maj9": "",
    "maj11": "",
    "maj13": "",
    "dom7": "",
    "6": "",
    "9": "",
    "11": "",
    "13": "",
    "sus2": "",
    "sus4": "",
    "add9": "",
    "aug": "",
    "power": "",
    # minor triad family
    "min": "m",
    "min7": "m",
    "min9": "m",
    "min11": "m",
    "min13": "m",
    # tonally-distinct qualities: no safe triad fallback → DROP (None)
    "dim": None,
    "dim7": None,
    "m7b5": None,
}


def _candidate_labels(label: str) -> list[str]:
    """Ordered lookup keys for a chord: exact, then degraded toward a triad.

    Returns only keys that are worth looking up:
    - Always starts with the exact label (e.g. "Am7", "Am9").
    - Appends the degraded label when the quality has a safe triad equivalent
      (e.g. min7 → "Am", maj9 → "A").  A None sentinel means the quality is
      tonally distinct (dim, dim7, m7b5) — no fallback is added, so if the
      exact shape is absent the chord is dropped rather than shown wrongly.
    - As a last resort, appends the bare root (handles slash chords like "D/F#"
      whose suffix is "" after root extraction by parse_chord).
    """
    parts = parse_chord(label)
    if not parts.root:
        return [label]

    candidates = [label]  # exact hit first

    degrade_suffix = _DEGRADE_SUFFIX.get(parts.quality)  # None → no safe fallback
    if degrade_suffix is not None:
        degraded = f"{parts.root}{degrade_suffix}"
        if degraded != label:  # skip if degraded == exact (avoids useless duplicate)
            candidates.append(degraded)
        # last-resort bare root (useful for slash chords and bare major triads)
        if parts.root != degraded:
            candidates.append(parts.root)

    return candidates


# ---------------------------------------------------------------------------
# G3.1 — Movable-shape generator
# ---------------------------------------------------------------------------

_NOTES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def _root_semitone(root: str) -> int | None:
    """Return 0-11 semitone index for a root note name, or None if unrecognised."""
    note = _FLAT_TO_SHARP.get(root, root)
    try:
        return _NOTES_SHARP.index(note)
    except ValueError:
        return None


# Open-chord fret shapes used as the template for barre transposition.
# Index 0 = low E string, index 5 = high e string.
# -1 means muted.  Shapes are defined at fret 0 (open position).
_MOVABLE_TEMPLATES: dict[tuple[str, str], dict] = {
    # (shape_name, quality) -> {frets, fingers, root_string (0-indexed), root_semitone}
    # E-shape major: root on string 0 (low E = semitone 4)
    ("E", "maj"): {
        "open_frets":   [0, 2, 2, 1, 0, 0],
        "open_fingers": [0, 2, 3, 1, 0, 0],
        "root_string":  0,   # string 0 = low E
        "root_pitch":   4,   # E = semitone 4
    },
    # Em-shape minor: root on string 0
    ("Em", "min"): {
        "open_frets":   [0, 2, 2, 0, 0, 0],
        "open_fingers": [0, 2, 3, 0, 0, 0],
        "root_string":  0,
        "root_pitch":   4,
    },
    # A-shape major: root on string 1 (A = semitone 9)
    # String 5 (high e) barred at same fret as string 1.
    ("A", "maj"): {
        "open_frets":   [-1, 0, 2, 2, 2, 0],
        "open_fingers": [ 0, 0, 1, 2, 3, 0],
        "root_string":  1,   # string 1 = A
        "root_pitch":   9,   # A = semitone 9
        "barre_string": 5,   # high-e barred at same fret as root
    },
    # Am-shape minor: root on string 1
    ("Am", "min"): {
        "open_frets":   [-1, 0, 2, 2, 1, 0],
        "open_fingers": [ 0, 0, 2, 3, 1, 0],
        "root_string":  1,
        "root_pitch":   9,
        "barre_string": 5,
    },
}

# Quality -> ordered list of template shapes to try.
# E-shape preferred for major (more common in literature); Em preferred for minor.
_SHAPE_PRIORITY: dict[str, list[str]] = {
    "maj":  ["E", "A"],    # try E-shape first, A-shape second
    "min":  ["Em", "Am"],
    "dom7": ["E", "A"],    # degrade dom7/maj7/min7 to the triad barre shape
    "maj7": ["E", "A"],
    "min7": ["Em", "Am"],
}


def _guitar_barre_shape(root: str, quality: str, prefer_low_fret: bool = False) -> dict | None:
    """Return a movable-barre fret/finger dict for guitar, or None if unsupported.

    The returned dict has keys ``frets`` (list[int]) and ``fingers`` (list[int]).
    Fret numbers are absolute (capo-unaware).  -1 = muted string.

    When ``prefer_low_fret=True`` (beginner mode) the A-shape (lower fret for
    roots Bb..G) is tried before the E-shape.

    In the default mode, E-shape is preferred when its barre fret is <= 7
    (comfortable reach); for higher positions the A-shape (which lands lower)
    is tried first so the player gets the most playable shape.

    Algorithm
    ---------
    For each candidate template (ordered by ``_SHAPE_PRIORITY``):
      1. Compute ``fret = (root_semitone - template.root_pitch) % 12``.
      2. Shift every non-muted open fret by ``fret``.
      3. Apply the barre_string override if the template has one.
    Return the first shape whose highest fret <= 12 (playable on a standard neck).
    """
    root_sem = _root_semitone(root)
    if root_sem is None:
        return None

    shape_names = list(_SHAPE_PRIORITY.get(quality, []))
    if not shape_names:
        return None

    if len(shape_names) >= 2:
        def fret_for_shape(sn: str) -> int:
            tmpl_q = "maj" if sn in ("E", "A") else "min"
            t = _MOVABLE_TEMPLATES.get((sn, tmpl_q))
            if t is None:
                return 99
            return (root_sem - t["root_pitch"]) % 12

        if prefer_low_fret:
            # Beginner: always sort by ascending fret (lower fret = easier reach)
            shape_names = sorted(shape_names, key=fret_for_shape)
        else:
            # Default: prefer E-shape when its fret is <= 7 (comfortable);
            # for higher positions, prefer the lower-fret A-shape instead.
            first_fret = fret_for_shape(shape_names[0])
            if first_fret > 7:
                shape_names = sorted(shape_names, key=fret_for_shape)

    for shape_name in shape_names:
        # Match quality to the template's canonical quality (maj/min).
        tmpl_quality = "maj" if shape_name in ("E", "A") else "min"
        tmpl = _MOVABLE_TEMPLATES.get((shape_name, tmpl_quality))
        if tmpl is None:
            continue

        fret = (root_sem - tmpl["root_pitch"]) % 12  # 0-11
        open_frets = tmpl["open_frets"]
        new_frets = [f + fret if f >= 0 else -1 for f in open_frets]

        # Apply barre override: the high-e string (or similar) is held by the
        # barre finger at the root fret, not individually fingered.
        barre_str = tmpl.get("barre_string")
        if barre_str is not None:
            new_frets[barre_str] = fret  # barre at root fret

        # Reject if any note is above fret 12 (unplayable for most learners).
        if max(f for f in new_frets if f >= 0) > 12:
            continue

        # Build finger positions: barre finger (1) on all strings at barre fret,
        # then incremental fingers for higher notes.
        fingers = list(tmpl["open_fingers"])
        for i, f in enumerate(new_frets):
            if f < 0:
                fingers[i] = 0
            elif f == fret:
                fingers[i] = 1  # barre
            else:
                # Preserve relative finger numbering from the open template.
                fingers[i] = tmpl["open_fingers"][i] if fret == 0 else max(tmpl["open_fingers"][i], 2)

        return {"frets": new_frets, "fingers": fingers}

    return None  # quality not supported by any movable template


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
