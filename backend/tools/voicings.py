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
#   - major-family (maj, maj7, maj9, maj11, maj13, dom7, 6, 9, 11, 13, add9,
#     power): degrade to the bare major triad ("").
#   - minor-family (min, min7, min9, min11, min13): degrade to the minor triad ("m").
#   - dim / dim7 / m7b5 / aug / sus2 / sus4: these are tonally DISTINCT from
#     major/minor triads. Showing an Am shape for "Adim" — or the C-major open
#     shape for "Csus4"/"Caug" (Phase 4 G3, VOICE-SUS) — would be musically
#     WRONG and mislead the player. We therefore map them to None (sentinel) so
#     _candidate_labels returns only the exact label — if neither the table nor
#     the movable-template generator has a correct shape, the chord gets a
#     no_voicing marker rather than a wrong shape.
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
    "add9": "",
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
    "aug": None,
    "sus2": None,
    "sus4": None,
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
        # last-resort bare root (useful for slash chords and bare major triads).
        # Only append for the MAJOR family (degrade_suffix == "") — for minor chords
        # the bare root is the major triad which would be musically wrong (Fm → F).
        if degrade_suffix == "" and parts.root != degraded:
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
    # Esus4-shape: root on string 0 (E A D A B E -> root, 4th doubled, 5th)
    ("Esus4", "sus4"): {
        "open_frets":   [0, 2, 2, 2, 0, 0],
        "open_fingers": [0, 2, 3, 4, 0, 0],
        "root_string":  0,
        "root_pitch":   4,
    },
    # Asus4-shape: root on string 1
    ("Asus4", "sus4"): {
        "open_frets":   [-1, 0, 2, 2, 3, 0],
        "open_fingers": [ 0, 0, 1, 2, 4, 0],
        "root_string":  1,
        "root_pitch":   9,
        "barre_string": 5,
    },
    # Asus2-shape: root on string 1
    ("Asus2", "sus2"): {
        "open_frets":   [-1, 0, 2, 2, 0, 0],
        "open_fingers": [ 0, 0, 2, 3, 0, 0],
        "root_string":  1,
        "root_pitch":   9,
        "barre_string": 5,
    },
    # Aaug-shape: root on string 1 (A F A C# = root, #5, root, 3rd)
    ("Aaug", "aug"): {
        "open_frets":   [-1, 0, 3, 2, 2, -1],
        "open_fingers": [ 0, 0, 4, 2, 3, 0],
        "root_string":  1,
        "root_pitch":   9,
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
    "sus4": ["Esus4", "Asus4"],
    "sus2": ["Asus2"],
    "aug":  ["Aaug"],
}


def _template_for(shape_name: str, quality: str) -> dict | None:
    """Resolve a movable template for (shape, quality).

    Exact (shape, quality) first; the classic E/A/Em/Am shapes double as the
    degraded triad target for 7th-family qualities (dom7 -> E-shape major).
    """
    tmpl = _MOVABLE_TEMPLATES.get((shape_name, quality))
    if tmpl is None and shape_name in ("E", "A"):
        tmpl = _MOVABLE_TEMPLATES.get((shape_name, "maj"))
    if tmpl is None and shape_name in ("Em", "Am"):
        tmpl = _MOVABLE_TEMPLATES.get((shape_name, "min"))
    return tmpl


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
            t = _template_for(sn, quality)
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
        tmpl = _template_for(shape_name, quality)
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


# ---------------------------------------------------------------------------
# G3.2 — Piano voicing generator
# ---------------------------------------------------------------------------

# Intervals (semitones above root) for each canonical quality.
# Qualities not listed here return None (no piano voicing defined).
_PIANO_INTERVALS: dict[str, list[int]] = {
    "maj":   [0, 4, 7],
    "min":   [0, 3, 7],
    "dom7":  [0, 4, 7, 10],
    "maj7":  [0, 4, 7, 11],
    "min7":  [0, 3, 7, 10],
    "dim":   [0, 3, 6],
    "dim7":  [0, 3, 6, 9],
    "m7b5":  [0, 3, 6, 10],
    "aug":   [0, 4, 8],
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
    "maj9":  [0, 4, 7, 11, 14],
    "min9":  [0, 3, 7, 10, 14],
    "9":     [0, 4, 7, 10, 14],
    "6":     [0, 4, 7, 9],
    "min13": [0, 3, 7, 10, 14, 17, 21],
    "maj13": [0, 4, 7, 11, 14, 17, 21],
    "13":    [0, 4, 7, 10, 14, 17, 21],
    "add9":  [0, 4, 7, 14],
}


def _midi_to_note_name(midi: int) -> str:
    """Convert a MIDI pitch to a note name with octave, e.g. 60 -> 'C4'."""
    octave = (midi // 12) - 1
    return f"{_NOTES_SHARP[midi % 12]}{octave}"


def _piano_chord_voicing(root: str, quality: str) -> dict | None:
    """Generate a closed-position piano voicing from chord-tone intervals.

    Returns ``{"right_hand": list[str], "left_hand": list[str]}`` or ``None``
    when the quality has no defined interval set (e.g. 'power').

    Right hand starts at C4 (MIDI 60) for root C; other roots are offset
    accordingly.  Notes that would exceed E5 (MIDI 76) wrap down an octave
    so the voicing stays in a singable mid-range.
    """
    intervals = _PIANO_INTERVALS.get(quality)
    if intervals is None:
        return None

    root_sem = _root_semitone(root)
    if root_sem is None:
        return None

    # Anchor: place the root in octave 4 (C4 = MIDI 60).
    root_midi = 60 + root_sem  # C4..B4

    # Build right-hand notes as MIDI values first so we can sort them.
    right_hand_midi: list[int] = []
    for interval in intervals:
        note_midi = root_midi + interval
        # If the note is above E5 (MIDI 76), move it down an octave so we stay
        # within a comfortable single-octave span for beginners.
        if note_midi > 76:
            note_midi -= 12
        right_hand_midi.append(note_midi)
    # Sort ascending so the voicing is always in pitch order regardless of
    # which notes were pulled down by the octave-cap above.
    right_hand_midi.sort()
    right_hand = [_midi_to_note_name(m) for m in right_hand_midi]

    # Left hand: just the root in octave 3.
    left_hand = [_midi_to_note_name(root_midi - 12)]

    return {"right_hand": right_hand, "left_hand": left_hand}


def _quality_chain(quality: str) -> list[str]:
    """Return quality candidates from specific to general for barre lookup.

    e.g. 'min7' -> ['min7', 'min']  so we first try an Em7-barre (not defined)
    then fall through to Em-barre (defined).
    """
    chain = [quality]
    # Broaden minor extensions to 'min', major extensions to 'maj'.
    # sus2/sus4/aug are deliberately NOT broadened to 'maj' — they have their
    # own movable templates, and a major barre would be a wrong shape (G3).
    if quality in ("min7", "min9", "min11", "min13"):
        chain.append("min")
    elif quality in ("maj7", "maj9", "maj11", "maj13", "dom7", "6", "9", "11", "13", "add9", "power"):
        chain.append("maj")
    elif quality == "dim7":
        chain.append("dim")
    return chain


def get_chord_diagrams(
    chords: list[str],
    instrument: Instrument = "guitar",
    difficulty: str = "intermediate",
) -> list[ChordDiagram]:
    """Return a ChordDiagram for every unique chord in the progression.

    Lookup order (guitar/ukulele/bass):
      1. Curated open-chord table (exact label).
      2. Degrade-by-quality fallback in the curated table (e.g. Am7 -> Am).
      3. Movable barre shape (guitar) or root-note shape (bass/ukulele).
      4. If nothing found: ChordDiagram(no_voicing=True) -- never silently dropped.

    Lookup order (piano):
      1. Curated _PIANO_TRIADS table (exact or degraded).
      2. Programmatic _piano_chord_voicing generator.
      3. no_voicing marker.

    The original chord label is always preserved on the returned diagram so
    the UI can display 'Am7' even when the shape fell back to Am.
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
        parts = parse_chord(c)
        shape: dict | None = None

        if instrument == "piano":
            # Piano lookup order:
            #   1. Exact hit in curated _PIANO_TRIADS
            #   2. Programmatic generator (exact quality — avoids degrading dom7 to
            #      the bare major triad when we can produce a proper voicing)
            #   3. no_voicing marker
            shape = table.get(c)
            if shape is None and parts.root:
                piano_v = _piano_chord_voicing(parts.root, parts.quality)
                if piano_v:
                    shape = piano_v
        else:
            # Guitar / ukulele / bass lookup order:
            # -- Step 1 + 2: curated table (exact then degraded) --
            for key in _candidate_labels(c):
                shape = table.get(key)
                if shape:
                    break

            # -- Step 3: programmatic barre generator (guitar only) --
            if shape is None and parts.root and instrument == "guitar":
                prefer_low = difficulty == "beginner"
                for q in _quality_chain(parts.quality):
                    shape = _guitar_barre_shape(parts.root, q, prefer_low_fret=prefer_low)
                    if shape:
                        break

        # -- Step 4: emit no_voicing marker instead of dropping --
        if shape is None or not parts.root:
            diagrams.append(
                ChordDiagram(chord=c, instrument=instrument, no_voicing=True)
            )
        else:
            diagrams.append(
                ChordDiagram(chord=c, instrument=instrument, no_voicing=False, **shape)
            )

    return diagrams
