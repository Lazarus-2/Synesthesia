"""
music21-backed Roman-numeral analysis.

Public API
----------
analyze_roman(chords, key_str) -> RomanAnalysis

Falls back to the legacy hand-rolled mapper when music21 is not importable
so the graph keeps running in environments without music21 installed.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.schemas import ChordEvent, RomanAnalysis

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flat-conversion helper (music21 uses '-' for flats, we use 'b')
# ---------------------------------------------------------------------------

_ROOT_FLAT_RE = re.compile(r"^([A-G])b")
_BASS_FLAT_RE = re.compile(r"(/[A-G])b")


def _to_m21(label: str) -> str:
    """Convert a chord-symbol label to music21 ``ChordSymbol``-compatible form.

    music21 uses the MIDI/classical convention of ``B-`` for B-flat, whereas
    the audio-chord-recognition output uses ``Bb``.  This function rewrites the
    root and (if present) the slash-bass note.

    Only the letter immediately following a capital note name is replaced:
    ``Bb``→``B-``, ``Eb7``→``E-7``, ``G/Bb``→``G/B-``.
    Sharps, natural notes, and chord-quality suffixes are left unchanged.
    """
    if not label:
        return label
    # Root flat first
    label = _ROOT_FLAT_RE.sub(lambda m: m.group(1) + "-", label)
    # Slash-bass flat (e.g. G/Bb -> G/B-)
    label = _BASS_FLAT_RE.sub(lambda m: m.group(1) + "-", label)
    return label


# ---------------------------------------------------------------------------
# Roman numeral root extractor
# Handles figured-bass suffixes like V75#3, I6, viio, bVII, etc.
# ---------------------------------------------------------------------------

# Matches optional leading accidental + Roman numeral root (longest-first alternation)
_RN_ROOT_RE = re.compile(
    r"^([b#]?)(VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)", re.IGNORECASE
)
_DIATONIC_ROOTS = frozenset(
    "I II III IV V VI VII i ii iii iv v vi vii".split()
)
_NO_CHORD_RE = re.compile(r"^(N\.?C\.?|)$", re.IGNORECASE)


_CHROMATIC_SUFFIX_RE = re.compile(r"[#b]")

# Natural-minor modal degrees that carry a flat prefix in music21's notation but
# ARE diatonic to natural minor (and should NEVER be re-labelled as secondary dominants).
_NATURAL_MINOR_MODAL = frozenset({"bVII", "bVI", "bIII"})

# Diatonic minor-quality root numerals in a major key (ii, iii, vi, vii are diatonic;
# iv, i, v would be modal mixture / borrowed from parallel minor).
_MAJOR_DIATONIC_LOWER = frozenset({"ii", "iii", "vi", "vii"})

# Figured-bass junk on 7th chords: only digits/accidentals, containing a '7'
# AND at least one accidental (e.g. '75#3', 'b753', 'b75b3'). Plain inversion
# figures (6, 64, 65, 43, 42) never match — they carry real information.
_FIGURE_JUNK_RE = re.compile(r"^[\db#]+$")
_QUALITY_MARKS = ("o", "ø", "+")


def _simplify_figure(figure: str) -> str:
    """Normalise figured-bass noise on 7th chords to a plain '7'.

    ``V75#3`` → ``V7`` (harmonic-minor dominant), ``IVb753`` → ``IV7``,
    ``viiob753`` → ``viio7`` (ROMAN-FIG, Phase 4 G3). Quality marks (o/ø/+)
    and secondary slashes (``V7/IV``) are preserved; inversion figures
    (``I6``, ``V65``…) are untouched.
    """
    pre, sep, post = figure.partition("/")
    m = _RN_ROOT_RE.match(pre)
    if not m:
        return figure
    root = pre[: m.end()]
    suffix = pre[m.end():]
    quality = ""
    while suffix and suffix[0] in _QUALITY_MARKS:
        quality += suffix[0]
        suffix = suffix[1:]
    if (
        "7" in suffix
        and _CHROMATIC_SUFFIX_RE.search(suffix)
        and _FIGURE_JUNK_RE.match(suffix)
    ):
        suffix = "7"
    return f"{root}{quality}{suffix}{sep}{post}"


def _is_diatonic_primary(primary_figure: str) -> bool:
    """Return True if *primary_figure* is a plain diatonic numeral (no accidentals anywhere).

    Uses a regex to extract the Roman numeral root before any figured-bass
    suffix (which may contain digits, accidentals, or letters like in 'V75#3').

    A chord is non-diatonic if:
    - the root has a leading accidental (e.g. bVII, #IV), OR
    - the figured-bass suffix contains accidentals (e.g. II75#3 = D7 in C major,
      where the raised major 3rd signals a secondary dominant candidate).
    """
    m = _RN_ROOT_RE.match(primary_figure)
    if not m:
        return False
    acc, root = m.group(1), m.group(2)
    # Leading accidental on root -> borrowed / chromatic
    if acc:
        return False
    # Accidental in figured-bass suffix -> secondary dominant candidate
    suffix = primary_figure[m.end():]
    if _CHROMATIC_SUFFIX_RE.search(suffix):
        return False
    return root in _DIATONIC_ROOTS


# ---------------------------------------------------------------------------
# Core analysis helper
# ---------------------------------------------------------------------------

try:
    from music21 import harmony as m21_harmony
    from music21 import key as m21_key_mod
    from music21 import roman as m21_roman
    _MUSIC21_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MUSIC21_AVAILABLE = False


def smart_analyze(chord_sym: str, key_obj: m21_key_mod.Key) -> m21_roman.RomanNumeral | None:
    """Return a music21 ``RomanNumeral`` for *chord_sym* in *key_obj*, or ``None`` for no-chord tokens.

    Two-pass strategy avoids the ``preferSecondaryDominants=True`` pitfall
    that mis-labels diatonic chords (e.g. C-major tonic -> V/IV instead of I):

    1. Analyse *without* ``preferSecondaryDominants`` → gives clean diatonic figure.
    2. If the ``primaryFigure`` is non-diatonic (has leading ``#``/``b`` or is
       otherwise outside the diatonic set), re-analyse *with*
       ``preferSecondaryDominants=True`` and use the result only if
       ``secondaryRomanNumeral is not None`` (i.e. it genuinely is a secondary
       dominant like V/V).  Otherwise keep the non-diatonic borrowed label (bVII).

    Special case (I1): natural-minor modal degrees ``bVII``, ``bVI``, ``bIII``
    are diatonic to natural minor and should NEVER be relabelled as secondary
    dominants.  When Pass-1's figure is one of these and the key is minor, Pass-1
    is returned unconditionally.
    """
    # C1 fix: strip whitespace before the no-chord guard so '   ' is caught too.
    if not chord_sym or not chord_sym.strip() or _NO_CHORD_RE.match(chord_sym.strip()):
        return None

    m21_label = _to_m21(chord_sym)
    cs = m21_harmony.ChordSymbol(m21_label)
    rn: m21_roman.RomanNumeral = m21_roman.romanNumeralFromChord(cs, key_obj)

    if _is_diatonic_primary(rn.primaryFigure):
        return rn

    # I1 fix: natural-minor modal degrees are diatonic in minor — keep Pass-1.
    if (
        rn.primaryFigure in _NATURAL_MINOR_MODAL
        and hasattr(key_obj, "mode")
        and key_obj.mode == "minor"
    ):
        return rn

    # Blues guard (ROMAN-BLUES, Phase 4 G3): a dom7 built on the tonic or
    # subdominant is idiomatic blues/rock vocabulary (C7 as tonic, F7 as
    # subdominant in C) — keep the Pass-1 degree label (later simplified to
    # I7/IV7) instead of relabelling it as a secondary dominant (V7/IV).
    m_root = _RN_ROOT_RE.match(rn.primaryFigure)
    if m_root and not m_root.group(1):
        suffix = rn.primaryFigure[m_root.end():]
        if m_root.group(2).upper() in ("I", "IV") and "7" in suffix:
            return rn

    # Non-diatonic: try to identify as a secondary dominant
    rn2: m21_roman.RomanNumeral = m21_roman.romanNumeralFromChord(
        cs, key_obj, preferSecondaryDominants=True
    )
    return rn2 if rn2.secondaryRomanNumeral is not None else rn


# ---------------------------------------------------------------------------
# Suspended-chord handling (ROMAN-SUS, Phase 4 G3)
# ---------------------------------------------------------------------------

_SUS_QUALITIES = ("sus2", "sus4")


def _sus_roman(root: str, sus_quality: str, key_obj: m21_key_mod.Key):
    """Roman pieces for a sus chord: ``(rn_of_root_triad, numeral, function)``.

    music21's ``romanNumeralFromChord`` has no concept of suspensions — it
    reads Csus4 = {C,F,G} as some inverted minor sonority (``i54``) and the
    pipeline then mislabels it borrowed/chromatic. A sus chord functions as
    its scale degree, so we analyse the plain triad on the same root and
    present ``<DEGREE>susN`` (e.g. ``Vsus4``). The root-triad RomanNumeral is
    returned so the cadence pass can treat e.g. Gsus4→C as dominant motion.
    """
    try:
        cs = m21_harmony.ChordSymbol(_to_m21(root))
        rn_root = m21_roman.romanNumeralFromChord(cs, key_obj)
    except Exception:
        return None
    m = _RN_ROOT_RE.match(rn_root.primaryFigure)
    if not m:
        return None
    acc, degree = m.group(1), m.group(2)
    numeral = f"{acc}{degree.upper()}{sus_quality}"
    return rn_root, numeral, harmonic_function(rn_root)


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

_LEADING_ACCIDENTAL_RE = re.compile(r"^[b#]")


def is_secondary(rn: m21_roman.RomanNumeral) -> bool:
    """True if *rn* is a secondary dominant (figure contains '/', e.g. V7/V)."""
    return rn.secondaryRomanNumeral is not None


def _is_modal_mixture(rn: m21_roman.RomanNumeral) -> bool:
    """True if *rn* is a modal-mixture chord in a major key.

    Catches the case where a chord has a lowercase (minor-quality) root figure
    without a leading accidental but is NOT diatonic to the major key.
    Example: ``iv`` (Fm) in C major — music21 returns figure ``'iv'`` with no
    leading ``b`` or ``#``, yet it is clearly borrowed from C minor.

    Diatonic minor-quality degrees in a major key are ``ii``, ``iii``, ``vi``,
    ``vii`` — everything else (``i``, ``iv``, ``v``) is modal mixture.
    """
    if is_secondary(rn):
        return False
    if not (hasattr(rn, "key") and rn.key is not None and rn.key.mode == "major"):
        return False
    m = _RN_ROOT_RE.match(rn.primaryFigure)
    if not m:
        return False
    acc, root = m.group(1), m.group(2)
    if acc:
        # Leading accidental is already caught by is_borrowed via _LEADING_ACCIDENTAL_RE
        return False
    # Lowercase root without accidental that is NOT a diatonic minor degree
    return root[0].islower() and root.lower() not in _MAJOR_DIATONIC_LOWER


def is_borrowed(rn: m21_roman.RomanNumeral) -> bool:
    """True if *rn* is a borrowed / modal-mixture chord (not a secondary dominant).

    Two detection paths:
    1. Leading accidental on the figure (e.g. ``bVII``, ``bVI`` in major).
    2. Modal mixture: minor-quality figure without accidental at a normally
       major-quality scale degree in a major key (e.g. ``iv`` = Fm in C major).
    """
    if is_secondary(rn):
        return False
    return bool(_LEADING_ACCIDENTAL_RE.match(rn.figure)) or _is_modal_mixture(rn)


# ---------------------------------------------------------------------------
# Harmonic function classifier
# ---------------------------------------------------------------------------

_FUNC_MAP: dict[str, str] = {
    "I":    "tonic",
    "i":    "tonic",
    "II":   "supertonic",
    "ii":   "supertonic",
    "III":  "mediant",
    "iii":  "mediant",
    "IV":   "subdominant",
    "iv":   "subdominant",
    "V":    "dominant",
    "v":    "dominant",
    "VI":   "submediant",
    "vi":   "submediant",
    "VII":  "leading_tone",
    "vii":  "leading_tone",
}


def harmonic_function(rn: m21_roman.RomanNumeral) -> str:
    """Map a ``RomanNumeral`` to a pedagogical function label.

    Priority order:
    1. Secondary dominant  → ``'secondary_dominant'``
    2. Borrowed chord in **major** key (leading accidental on figure, OR modal
       mixture — e.g. ``iv`` = Fm in C major) → ``'chromatic'``.
    3. All other chords (diatonic + borrowed-in-minor like bVI/bVII which are
       natural-minor degrees) → lookup root via ``_FUNC_MAP``.
       In minor, music21 labels natural-minor chords bVI / bVII / III with
       flat prefixes, but they carry clear functional meaning (submediant,
       leading_tone, mediant) — map via root without the accidental.
    4. Fallback → ``'chromatic'``
    """
    if is_secondary(rn):
        return "secondary_dominant"

    # Modal mixture in major (no leading accidental, but minor-quality non-diatonic root)
    if _is_modal_mixture(rn):
        return "chromatic"

    # Use regex-based root extraction so figured-bass suffixes like '75#3' don't interfere
    m = _RN_ROOT_RE.match(rn.primaryFigure)
    if not m:
        return "chromatic"
    acc, root = m.group(1), m.group(2)

    # In major mode: flat/sharp-prefixed chords are modal-mixture → chromatic
    if acc and hasattr(rn, "key") and rn.key is not None and rn.key.mode == "major":
        return "chromatic"

    # In minor mode (or no accidental): map root via _FUNC_MAP
    return _FUNC_MAP.get(root, "chromatic")


# ---------------------------------------------------------------------------
# Cadence detection
# ---------------------------------------------------------------------------

def _primary_base(rn: m21_roman.RomanNumeral) -> str:
    """Return the root numeral stripped of accidentals and extensions, uppercase."""
    m = _RN_ROOT_RE.match(rn.primaryFigure)
    if not m:
        return ""
    return m.group(2).upper()


def detect_cadence(
    prev: m21_roman.RomanNumeral,
    curr: m21_roman.RomanNumeral,
) -> str | None:
    """Classify the cadence type formed by the *prev* → *curr* motion.

    Returns one of ``'PAC'``, ``'IAC'``, ``'deceptive'``, ``'half'``,
    ``'plagal'``, or ``None`` if no standard cadence is detected.

    Rules (in priority order):
    - PAC  : V(7) → I, both root position (inversion == 0)
    - IAC  : V(7) → I, one or both inverted
    - Deceptive: V(7) → vi
    - Half : * → V (root position), preceded by I, ii, IV, or vi
    - Plagal: IV → I (root position)
    """
    pb = _primary_base(prev)
    cb = _primary_base(curr)
    p_inv = prev.inversion()
    c_inv = curr.inversion()

    if pb == "V" and cb == "I":
        if p_inv == 0 and c_inv == 0:
            return "PAC"
        return "IAC"

    if pb == "V" and cb == "VI":
        return "deceptive"

    if cb == "V" and c_inv == 0 and pb in ("I", "II", "IV", "VI"):
        return "half"

    if pb == "IV" and cb == "I" and c_inv == 0:
        return "plagal"

    return None


# ---------------------------------------------------------------------------
# Modulation detection
# ---------------------------------------------------------------------------

_WINDOW = 4            # minimum consecutive chords to confirm a new key
_SCORE_THRESHOLD = 0.65  # KS correlation threshold (music21 Key.correlationCoefficient)
_MAX_MODULATIONS = 8   # cap to prevent runaway detection on random/noisy progressions


def detect_modulations(
    chord_symbols: list[str],
    home_key: m21_key_mod.Key,
    max_modulations: int = _MAX_MODULATIONS,
) -> list[dict]:
    """Scan *chord_symbols* for sustained modulations away from *home_key*.

    Uses a sliding window of ``_WINDOW`` chords; O(n) in the number of
    chord symbols (two stream-analysis calls per candidate window).  For each
    window position where the window does not fit *home_key*, runs music21's
    ``stream.analyze('key')`` on the window.  A new key is reported only when:

    * the detected key differs from both the tracking key and home key,
    * the next overlapping window confirms the same key, AND
    * the Krumhansl-Schmuckler ``correlationCoefficient`` of the detected key
      meets ``_SCORE_THRESHOLD`` (≥ 0.65) to filter weak / ambiguous matches.

    Detection stops once ``max_modulations`` (default ``_MAX_MODULATIONS = 8``)
    entries have been collected to prevent over-reporting on random progressions.

    Returns a list of ``{"to_key": str, "at_index": int}`` dicts.
    """
    if not _MUSIC21_AVAILABLE:  # pragma: no cover
        return []

    from music21 import stream as m21_stream

    modulations: list[dict] = []
    n = len(chord_symbols)
    if n < _WINDOW:
        return []

    current_key_str = str(home_key)
    home_key_str = str(home_key)

    i = 0
    while i <= n - _WINDOW:
        # I3 fix: stop once max_modulations cap is reached
        if len(modulations) >= max_modulations:
            break

        window_syms = chord_symbols[i: i + _WINDOW]
        s = m21_stream.Stream()
        for sym in window_syms:
            try:
                cs = m21_harmony.ChordSymbol(_to_m21(sym))
                cs.duration.quarterLength = 1.0
                s.append(cs)
            except Exception:
                pass

        if len(s) < _WINDOW:
            i += 1
            continue

        detected: m21_key_mod.Key = s.analyze("key")
        detected_str = str(detected)

        # I3 fix: gate on KS correlation coefficient to filter weak detections
        score = getattr(detected, "correlationCoefficient", 1.0)
        if score < _SCORE_THRESHOLD:
            i += 1
            continue

        if detected_str != current_key_str and detected_str != home_key_str:
            # Confirm: does the *next* window also agree?
            if i + _WINDOW < n:
                s2 = m21_stream.Stream()
                for sym in chord_symbols[i + 1: i + 1 + _WINDOW]:
                    try:
                        cs2 = m21_harmony.ChordSymbol(_to_m21(sym))
                        cs2.duration.quarterLength = 1.0
                        s2.append(cs2)
                    except Exception:
                        pass
                confirmed: m21_key_mod.Key = s2.analyze("key")
                if str(confirmed) == detected_str:
                    modulations.append({"to_key": detected_str, "at_index": i})
                    current_key_str = detected_str
                    i += _WINDOW  # skip ahead past confirmed window
                    continue
        i += 1

    return modulations


# ---------------------------------------------------------------------------
# No-music21 fallback
# ---------------------------------------------------------------------------

def _legacy_fallback(
    chords: list[dict | ChordEvent],
    key_str: str,
) -> RomanAnalysis:
    """Hand-rolled diatonic mapper used when music21 is unavailable.

    Reproduces the original ``roman_analysis_node`` logic (nodes.py:425-530)
    but WITHOUT the 8-chord truncation and WITHOUT dedup on the full progression
    (dedup is only applied to ``summary_progression`` for back-compat).
    Non-diatonic chords are labelled ``'?'`` rather than the broken placeholder
    ``'bdegree'``/``'#degree'``.
    """
    from backend.schemas import RomanAnalysis

    _notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    _enharmonics = {
        "DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#",
        "CB": "B",  # C-flat = B
        "FB": "E",  # F-flat = E
    }

    def _pc(note: str) -> int:
        n = note.upper()
        n = _enharmonics.get(n, n)
        return _notes.index(n) if n in _notes else 0

    m = re.match(r"^([A-G][b#]?)\s+(major|minor)$", key_str.strip(), re.IGNORECASE)
    key_root = m.group(1) if m else "C"
    key_mode = m.group(2).lower() if m else "major"
    key_pc = _pc(key_root)

    diatonic_major = {0: "I", 2: "ii", 4: "iii", 5: "IV", 7: "V", 9: "vi", 11: "vii°"}
    diatonic_minor = {0: "i", 2: "ii°", 3: "III", 5: "iv", 7: "v", 8: "VI", 10: "VII"}
    func_major = {0: "tonic", 2: "supertonic", 4: "mediant", 5: "subdominant",
                  7: "dominant", 9: "submediant", 11: "leading_tone"}
    func_minor = {0: "tonic", 2: "supertonic", 3: "mediant", 5: "subdominant",
                  7: "dominant", 8: "submediant", 10: "leading_tone"}

    dmap = diatonic_minor if key_mode == "minor" else diatonic_major
    fmap = func_minor if key_mode == "minor" else func_major

    progression: list[str] = []
    function: list[str] = []

    for c in chords:
        sym = c.get("chord") if isinstance(c, dict) else c.chord
        if not sym or sym.upper() in ("N.C.", "N", ""):
            continue
        cm = re.match(r"^([A-G][b#]?)", sym)
        if not cm:
            continue
        c_root = cm.group(1)
        offset = (_pc(c_root) - key_pc) % 12
        progression.append(dmap.get(offset, "?"))
        function.append(fmap.get(offset, "chromatic"))

    deduped: list[str] = []
    for num in progression:
        if not deduped or deduped[-1] != num:
            deduped.append(num)

    return RomanAnalysis(
        key=key_str,
        progression=progression,
        function=function,
        summary_progression=deduped[:8],
        entries=[],
        cadences=[],
        modulations=[],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_roman(
    chords: list[dict | ChordEvent],
    key_str: str,
) -> RomanAnalysis:
    """Produce a fully enriched ``RomanAnalysis`` for *chords* in *key_str*.

    Parameters
    ----------
    chords:
        Either a list of ``ChordEvent`` instances or plain dicts with at
        least ``chord``, ``start``, ``end`` keys.
    key_str:
        Key string as produced by the ML layer, e.g. ``'C major'``, ``'A minor'``.

    Returns
    -------
    RomanAnalysis
        With ``entries`` (time-aligned), ``progression``, ``function`` (legacy back-compat),
        ``summary_progression`` (≤8 deduped for compact UI), ``cadences``, ``modulations``.

    Falls back to the legacy hand-rolled mapper when music21 is unavailable.
    """
    from backend.schemas import RomanAnalysis, RomanEntry

    if not _MUSIC21_AVAILABLE:
        return _legacy_fallback(chords, key_str)

    # --- Parse key (use module-level re, not a re-import) ---
    m = re.match(r"^([A-G][b#]?)\s+(major|minor)$", key_str.strip(), re.IGNORECASE)
    if m:
        tonic = m.group(1)
        mode = m.group(2).lower()
        # music21 uses lowercase tonic for minor keys
        m21_tonic = tonic if mode == "major" else tonic.lower()
        home_key = m21_key_mod.Key(m21_tonic, mode)
    else:
        home_key = m21_key_mod.Key("C", "major")

    entries: list[RomanEntry] = []
    chord_symbols: list[str] = []
    # I2 fix: retain RomanNumeral objects aligned with entries so the cadence
    # pass can reuse them rather than calling smart_analyze a second time.
    rn_objects: list[m21_roman.RomanNumeral] = []

    from backend.tools.chords import parse_chord

    for c in chords:
        if isinstance(c, dict):
            sym, start, end = c.get("chord", ""), float(c.get("start", 0)), float(c.get("end", 0))
        else:
            sym, start, end = c.chord, c.start, c.end

        # ROMAN-SUS (Phase 4 G3): suspensions bypass romanNumeralFromChord —
        # see _sus_roman. Entry is degree-based: Gsus4 in C -> 'Vsus4'.
        parts = parse_chord(sym) if sym else None
        if parts and parts.root and parts.quality in _SUS_QUALITIES:
            sus = _sus_roman(parts.root, parts.quality, home_key)
            if sus is not None:
                rn_root, numeral, func = sus
                chord_symbols.append(sym)
                rn_objects.append(rn_root)
                entries.append(
                    RomanEntry(
                        chord=sym,
                        numeral=numeral,
                        function=func,
                        inversion=0,
                        is_secondary=False,
                        is_borrowed=False,
                        cadence=None,
                        start=start,
                        end=end,
                    )
                )
            continue

        # C1 fix: per-chord guard so a bad symbol (e.g. 'Bbb', '   ') is skipped
        # rather than aborting the whole analysis.
        try:
            rn = smart_analyze(sym, home_key)
        except Exception:
            log.debug("roman: skipping unparseable chord %r", sym)
            continue
        if rn is None:
            continue  # skip N.C. tokens

        # Normalise figured-bass noise ('V75#3'→'V7', 'IVb753'→'IV7',
        # 'viiob753'→'viio7') for readability; inversions are preserved.
        figure = _simplify_figure(rn.figure)

        chord_symbols.append(sym)
        rn_objects.append(rn)
        entries.append(
            RomanEntry(
                chord=sym,
                numeral=figure,
                function=harmonic_function(rn),
                inversion=rn.inversion(),
                is_secondary=is_secondary(rn),
                is_borrowed=is_borrowed(rn),
                cadence=None,   # filled in cadence pass below
                start=start,
                end=end,
            )
        )

    # --- Cadence pass (I2 fix: reuse rn_objects, no second smart_analyze calls) ---
    cadences: list[dict] = []
    for i in range(1, len(rn_objects)):
        rn_prev = rn_objects[i - 1]
        rn_curr = rn_objects[i]
        cad = detect_cadence(rn_prev, rn_curr)
        if cad:
            entries[i] = entries[i].model_copy(update={"cadence": cad})
            cadences.append({"type": cad, "index": i})

    # --- Modulation pass ---
    modulations = detect_modulations(chord_symbols, home_key)

    # --- Legacy fields (back-compat for TheoryPanel.tsx and theory_chain) ---
    progression = [e.numeral for e in entries]
    function = [e.function for e in entries]

    # summary_progression: dedup consecutive then cap at 8 (for compact UI)
    deduped: list[str] = []
    for num in progression:
        if not deduped or deduped[-1] != num:
            deduped.append(num)
    summary_progression = deduped[:8]

    return RomanAnalysis(
        key=key_str,
        progression=progression,
        function=function,
        summary_progression=summary_progression,
        entries=entries,
        cadences=cadences,
        modulations=modulations,
    )
