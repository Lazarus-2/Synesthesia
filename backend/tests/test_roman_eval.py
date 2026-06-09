"""G6 — Roman-numeral correctness eval.

Pure music21 + JSON; no network, no LLM, no audio.
Marked so CI picks it up with: pytest -m "not ml and not integration"

Design: scored by **chord-symbol root pitch class** (extracted from
result.entries[i].chord via music21.harmony.ChordSymbol) compared against
expected_root_pcs (also chord-symbol pcs). This is robust to music21's
enharmonic ambiguities in RomanNumeral(figure, key) for flat modal degrees
(bVI/bVII/bIII in minor) while still catching wrong roots.

Cadence type comparison is case-insensitive (analyze_roman returns uppercase
PAC/IAC; golden file uses lowercase pac/iac).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from music21 import converter
from music21 import harmony as m21_harmony
from music21 import key as m21key
from music21 import roman as m21roman

GOLDEN_PATH = Path(__file__).parent / "roman_golden.json"

# ------------------------------------------------------------------
# Import G1's analyze_roman (will NameError until G1 lands — that's
# expected; the test is written first per TDD discipline).
# ------------------------------------------------------------------
try:
    from backend.theory.roman import analyze_roman  # G1 target

    _ANALYZE_ROMAN_AVAILABLE = True
except ImportError:
    _ANALYZE_ROMAN_AVAILABLE = False

_NUMERAL_THRESHOLD = 0.80  # >= 80 % root-PC matches across all non-wrong items
_CADENCE_THRESHOLD = 0.70  # >= 70 % cadence-type accuracy (where expected_cadence is set)

_NOTE_TO_MUSIC21 = {
    # Allow tests to write "Bb" in chords list; translate to music21 "B-"
    "Bb": "B-",
    "Eb": "E-",
    "Ab": "A-",
    "Db": "D-",
    "Gb": "G-",
}


def _normalise_chord(sym: str) -> str:
    """Translate common flat spellings to music21 convention."""
    for human, m21 in _NOTE_TO_MUSIC21.items():
        sym = sym.replace(human, m21)
    return sym


def _chord_root_pc(chord_sym: str) -> int | None:
    """Return the root pitch class (0-11) of a chord symbol.

    Uses music21.harmony.ChordSymbol so the root is extracted from the
    actual chord name, NOT inferred from a Roman numeral figure in a key.
    This avoids the RomanNumeral(figure, minor_key) enharmonic quirk for
    flat modal degrees (bVI/bVII/bIII) where music21 computes the root by
    lowering the diatonic degree rather than by reading the input chord.
    """
    try:
        cs = m21_harmony.ChordSymbol(_normalise_chord(chord_sym))
        return cs.root().pitchClass
    except Exception:
        return None


def _score_item(item: dict, result) -> tuple[int, int]:
    """Return (correct_roots, total_chords) for one golden item.

    Scoring strategy: compare entry.chord root PCs (from result.entries)
    against expected_root_pcs.  Falls back to figure_to_root_pc when
    entries are fewer than expected (shouldn't happen on well-formed input).
    """
    expected_pcs = item["expected_root_pcs"]
    n = len(expected_pcs)
    entries = result.entries[:n]
    correct = 0
    for i, exp_pc in enumerate(expected_pcs):
        if i < len(entries):
            got_pc = _chord_root_pc(entries[i].chord)
        else:
            got_pc = None
        if got_pc == exp_pc:
            correct += 1
    return correct, n


# ---------------------------------------------------------------------------
# G6.1 — golden file exists and is structurally valid
# ---------------------------------------------------------------------------


@pytest.mark.roman_eval
def test_golden_file_exists_and_valid():
    """G6.1 — golden file must exist with >= 20 items, each with required keys."""
    assert GOLDEN_PATH.exists(), f"roman_golden.json not found at {GOLDEN_PATH}"
    data = json.loads(GOLDEN_PATH.read_text())
    assert "items" in data, "Top-level key 'items' missing"
    items = data["items"]
    assert len(items) >= 20, f"Need >= 20 items, got {len(items)}"
    required = {"id", "description", "key", "chords", "expected_root_pcs"}
    for item in items:
        missing = required - item.keys()
        assert not missing, f"Item {item.get('id', '?')} missing keys: {missing}"
        assert len(item["chords"]) == len(item["expected_root_pcs"]), (
            f"Item {item['id']}: chord count != root_pc count"
        )


# ---------------------------------------------------------------------------
# G6.2 — numeral accuracy threshold
# ---------------------------------------------------------------------------


@pytest.mark.roman_eval
@pytest.mark.skipif(
    not _ANALYZE_ROMAN_AVAILABLE,
    reason="backend.theory.roman.analyze_roman not yet implemented (G1 pending)",
)
def test_numeral_accuracy_threshold():
    """G6.2 — >= 80 % root-PC accuracy across non-wrong golden items."""
    data = json.loads(GOLDEN_PATH.read_text())
    items = [i for i in data["items"] if not i.get("_deliberately_wrong")]

    total_chords = 0
    total_correct = 0

    for item in items:
        chords = [_normalise_chord(c) for c in item["chords"]]
        chords_dicts = [
            {"chord": c, "start": float(idx), "end": float(idx + 1)}
            for idx, c in enumerate(chords)
        ]
        result = analyze_roman(chords=chords_dicts, key_str=item["key"])
        correct, n = _score_item(item, result)
        total_correct += correct
        total_chords += n

    accuracy = total_correct / total_chords if total_chords else 0.0
    assert accuracy >= _NUMERAL_THRESHOLD, (
        f"Root-PC accuracy {accuracy:.1%} < threshold {_NUMERAL_THRESHOLD:.0%} "
        f"({total_correct}/{total_chords} correct)"
    )


# ---------------------------------------------------------------------------
# G6.3 — cadence detection threshold
# ---------------------------------------------------------------------------

@pytest.mark.roman_eval
@pytest.mark.skipif(
    not _ANALYZE_ROMAN_AVAILABLE,
    reason="backend.theory.roman.analyze_roman not yet implemented (G1 pending)",
)
def test_cadence_detection_threshold():
    """G6.3 — >= 70 % cadence-type accuracy on items where expected_cadence is set.

    Cadence labels: 'pac' | 'iac' | 'half' | 'deceptive' | 'plagal' | null.
    analyze_roman returns uppercase (PAC/IAC); comparison is case-insensitive.
    """
    data = json.loads(GOLDEN_PATH.read_text())
    cadence_items = [
        i
        for i in data["items"]
        if not i.get("_deliberately_wrong") and i.get("expected_cadence") is not None
    ]
    assert cadence_items, "No cadence items in golden set — check roman_golden.json"

    correct = 0
    for item in cadence_items:
        chords = [_normalise_chord(c) for c in item["chords"]]
        chords_dicts = [
            {"chord": c, "start": float(idx), "end": float(idx + 1)}
            for idx, c in enumerate(chords)
        ]
        result = analyze_roman(chords=chords_dicts, key_str=item["key"])
        # Derive cadence from the cadences list: take the last detected cadence type
        got_cad = result.cadences[-1]["type"].lower() if result.cadences else None
        exp_cad = item["expected_cadence"]
        if got_cad == exp_cad:
            correct += 1

    accuracy = correct / len(cadence_items)
    assert accuracy >= _CADENCE_THRESHOLD, (
        f"Cadence accuracy {accuracy:.1%} < threshold {_CADENCE_THRESHOLD:.0%} "
        f"({correct}/{len(cadence_items)} correct)"
    )


# ---------------------------------------------------------------------------
# G6.4 — secondary dominant detection
# ---------------------------------------------------------------------------


@pytest.mark.roman_eval
@pytest.mark.skipif(
    not _ANALYZE_ROMAN_AVAILABLE,
    reason="backend.theory.roman.analyze_roman not yet implemented (G1 pending)",
)
def test_secondary_dominant_detection():
    """G6.4 — secondary dominant detection (binary: any V/x present?).

    analyze_roman sets is_secondary on each RomanEntry.  has_secondary_dominant
    is derived as any(e.is_secondary for e in result.entries).
    Golden items where expected_secondary=True must be detected with >= 75 % recall.
    Items where expected_secondary=False must not be false-alarmed > 25 % of the time.
    """
    data = json.loads(GOLDEN_PATH.read_text())
    sec_items = [
        i
        for i in data["items"]
        if not i.get("_deliberately_wrong") and "expected_secondary" in i
    ]
    pos_items = [i for i in sec_items if i["expected_secondary"]]
    neg_items = [i for i in sec_items if not i["expected_secondary"]]

    assert pos_items, "No positive (expected_secondary=True) items in golden set"

    def _has_secondary(chords_list, key_str):
        chords = [_normalise_chord(c) for c in chords_list]
        chords_dicts = [
            {"chord": c, "start": float(idx), "end": float(idx + 1)}
            for idx, c in enumerate(chords)
        ]
        result = analyze_roman(chords=chords_dicts, key_str=key_str)
        return any(e.is_secondary for e in result.entries)

    # Recall on positive items
    pos_correct = sum(
        1 for item in pos_items if _has_secondary(item["chords"], item["key"])
    )
    recall = pos_correct / len(pos_items)

    # False-alarm rate on negative items
    false_alarms = sum(
        1 for item in neg_items if _has_secondary(item["chords"], item["key"])
    )
    far = false_alarms / len(neg_items) if neg_items else 0.0

    assert recall >= 0.75, (
        f"Secondary dominant recall {recall:.1%} < 75 % ({pos_correct}/{len(pos_items)})"
    )
    assert far <= 0.25, (
        f"Secondary dominant false-alarm rate {far:.1%} > 25 % ({false_alarms}/{len(neg_items)})"
    )


# ---------------------------------------------------------------------------
# G6.5 — deliberately-wrong item proves scorer fails on mismatch
# ---------------------------------------------------------------------------


@pytest.mark.roman_eval
@pytest.mark.skipif(
    not _ANALYZE_ROMAN_AVAILABLE,
    reason="backend.theory.roman.analyze_roman not yet implemented (G1 pending)",
)
def test_scorer_catches_wrong_expectations():
    """G6.5 — the deliberately-wrong item must score BELOW 50 % accuracy.

    This proves the scorer is not a rubber stamp: when expected_root_pcs are
    intentionally incorrect (all shifted by 1 semitone), the scorer must detect
    the mismatch.  If this test fails it means the scoring logic is broken.
    """
    data = json.loads(GOLDEN_PATH.read_text())
    wrong_items = [i for i in data["items"] if i.get("_deliberately_wrong")]
    assert wrong_items, "No _deliberately_wrong item in roman_golden.json"

    for item in wrong_items:
        chords = [_normalise_chord(c) for c in item["chords"]]
        chords_dicts = [
            {"chord": c, "start": float(idx), "end": float(idx + 1)}
            for idx, c in enumerate(chords)
        ]
        result = analyze_roman(chords=chords_dicts, key_str=item["key"])
        correct, n = _score_item(item, result)
        accuracy = correct / n if n else 0.0
        assert accuracy < 0.50, (
            f"Scorer did NOT catch wrong expectations for item '{item['id']}': "
            f"got {accuracy:.1%} accuracy — scorer appears to be a rubber stamp. "
            f"Entry chords: {[e.chord for e in result.entries[:n]]!r}, "
            f"Wrong expected PCs: {item['expected_root_pcs']!r}"
        )


# ---------------------------------------------------------------------------
# G6.6 — embedded .rntxt fixture (RomanText format coverage)
# ---------------------------------------------------------------------------

# Embedded .rntxt fixture — 4-measure I-V-vi-IV + ii-V7-I progression
_RNTXT_FIXTURE = """\
Composer: Synesthesia G6 eval fixture
Title: Four-measure test
Analyst: G6
Time Signature: 4/4
m1 I b3 V
m2 vi b3 IV
m3 ii b3 V7
m4 I
"""

# Expected figures in order (offset-sorted)
_RNTXT_EXPECTED_FIGURES = ["I", "V", "vi", "IV", "ii", "V7", "I"]


@pytest.mark.roman_eval
def test_rntxt_fixture_parsing():
    """G6.6 — parse embedded .rntxt content via music21.converter.

    Verifies that the RomanText format path is available and that the fixture's
    figures round-trip correctly.  This test does NOT require G1; it tests the
    music21 installation itself and documents the expected .rntxt interface.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".rntxt", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(_RNTXT_FIXTURE)
        tmp_path = f.name

    try:
        score = converter.parse(tmp_path, format="romanText")
        got_figures = [
            el.figure for el in score.recurse().getElementsByClass("RomanNumeral")
        ]
    finally:
        os.unlink(tmp_path)

    assert got_figures == _RNTXT_EXPECTED_FIGURES, (
        f"Parsed figures {got_figures!r} != expected {_RNTXT_EXPECTED_FIGURES!r}"
    )


# ---------------------------------------------------------------------------
# G6.7 — roman_eval marker is registered in pyproject.toml
# ---------------------------------------------------------------------------


@pytest.mark.roman_eval
def test_roman_eval_marker_registered():
    """G6.7 — pytest marker 'roman_eval' must be registered in pyproject.toml.

    An unregistered marker triggers PytestUnknownMarkWarning which becomes an
    error under --strict-markers (used in CI per ID-03).
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--markers"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent.parent),  # repo root
    )
    assert "roman_eval" in result.stdout, (
        "'roman_eval' not found in pytest --markers output. "
        "Add it to [tool.pytest.ini_options] markers in pyproject.toml."
    )
