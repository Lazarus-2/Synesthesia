"""
G6 Roman-numeral correctness eval.

Offline, deterministic — no network, no LLM, no audio.
Uses music21 10.3.0 to score analyze_roman output against a hand-verified
golden set of 27 non-wrong items (plus 1 deliberately-wrong anti-stamp item).

Scoring strategy
----------------
Root pitch classes are extracted from result.entries[i].chord via
music21.harmony.ChordSymbol — NOT from RomanNumeral(figure, key).root().
The latter is unreliable for flat modal degrees (bVI/bVII/bIII) in minor
keys because music21 lowers the diatonic scale degree rather than reading
the input chord symbol.  Using ChordSymbol.root() is unambiguous.

Cadence comparison is case-insensitive: analyze_roman returns uppercase
(PAC/IAC/half/deceptive/plagal); the golden file uses lowercase.

Run:
    python -m backend.tests.eval_roman

CI integration:
    pytest backend/tests/ -m "not ml and not integration"
    (roman_eval marker carries neither ml nor integration, so it is included
    automatically by that CI filter)
"""

from __future__ import annotations

import json
from pathlib import Path

from music21 import harmony as m21_harmony

GOLDEN_PATH = Path(__file__).parent / "roman_golden.json"
NUMERAL_THRESHOLD = 0.80  # 80 % root-PC accuracy
CADENCE_THRESHOLD = 0.70  # 70 % cadence-type accuracy (where expected_cadence is set)

_NOTE_TO_MUSIC21 = {
    "Bb": "B-",
    "Eb": "E-",
    "Ab": "A-",
    "Db": "D-",
    "Gb": "G-",
}


def normalise_chord(sym: str) -> str:
    """Translate common flat spellings to music21 convention."""
    for human, m21 in _NOTE_TO_MUSIC21.items():
        sym = sym.replace(human, m21)
    return sym


def chord_root_pc(chord_sym: str) -> int | None:
    """Return root pitch class (0-11) from a chord symbol string.

    Uses music21.harmony.ChordSymbol so the root is extracted from the
    actual note name, not inferred from a Roman numeral in a key context.
    """
    try:
        cs = m21_harmony.ChordSymbol(normalise_chord(chord_sym))
        return cs.root().pitchClass
    except Exception:
        return None


def score_numerals(
    entries: list,
    expected_root_pcs: list[int],
) -> tuple[int, int]:
    """Return (n_correct, n_total) comparing entry chord PCs to expected root PCs."""
    n = min(len(entries), len(expected_root_pcs))
    correct = 0
    for i in range(n):
        if chord_root_pc(entries[i].chord) == expected_root_pcs[i]:
            correct += 1
    return correct, len(expected_root_pcs)


def run_eval(verbose: bool = True) -> dict:
    """Run the full Roman-numeral eval. Returns summary dict."""
    from backend.theory.roman import analyze_roman  # G1 target

    data = json.loads(GOLDEN_PATH.read_text())
    items = data["items"]
    non_wrong = [i for i in items if not i.get("_deliberately_wrong")]

    total_chords = 0
    total_correct = 0
    cadence_total = 0
    cadence_correct = 0
    secondary_total = 0
    secondary_correct = 0
    per_item = []

    for item in non_wrong:
        chords = [normalise_chord(c) for c in item["chords"]]
        chords_dicts = [
            {"chord": c, "start": float(idx), "end": float(idx + 1)}
            for idx, c in enumerate(chords)
        ]
        result = analyze_roman(chords=chords_dicts, key_str=item["key"])

        correct, n = score_numerals(result.entries, item["expected_root_pcs"])
        total_correct += correct
        total_chords += n
        item_acc = correct / n if n else 0.0

        # Cadence scoring (case-insensitive)
        exp_cad = item.get("expected_cadence")
        if exp_cad is not None:
            cadence_total += 1
            got_cad = result.cadences[-1]["type"].lower() if result.cadences else None
            if got_cad == exp_cad:
                cadence_correct += 1

        # Secondary dominant scoring
        if "expected_secondary" in item:
            secondary_total += 1
            got_sec = any(e.is_secondary for e in result.entries)
            if bool(got_sec) == bool(item["expected_secondary"]):
                secondary_correct += 1

        per_item.append(
            {
                "id": item["id"],
                "accuracy": item_acc,
                "got_entry_chords": [e.chord for e in result.entries[: len(item["chords"])]],
                "got_numerals": [e.numeral for e in result.entries[: len(item["chords"])]],
                "expected_root_pcs": item["expected_root_pcs"],
            }
        )
        if verbose:
            status = "OK  " if item_acc >= 0.75 else "WARN"
            print(f"  [{status}] {item['id']}: {item_acc:.0%} ({correct}/{n})")

    overall_acc = total_correct / total_chords if total_chords else 0.0
    cad_acc = cadence_correct / cadence_total if cadence_total else 0.0
    sec_acc = secondary_correct / secondary_total if secondary_total else 0.0

    summary = {
        "numeral_accuracy": overall_acc,
        "cadence_accuracy": cad_acc,
        "secondary_dominant_accuracy": sec_acc,
        "pass": overall_acc >= NUMERAL_THRESHOLD,
        "per_item": per_item,
    }

    if verbose:
        print(f"\nNumeral accuracy:            {overall_acc:.1%}  (threshold {NUMERAL_THRESHOLD:.0%})")
        print(f"Cadence detection accuracy:  {cad_acc:.1%}  (threshold {CADENCE_THRESHOLD:.0%})")
        print(f"Secondary dominant accuracy: {sec_acc:.1%}")
        print(f"Overall PASS: {summary['pass']}")

    return summary


if __name__ == "__main__":
    result = run_eval(verbose=True)
    raise SystemExit(0 if result["pass"] else 1)
