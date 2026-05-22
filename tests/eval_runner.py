"""
Evaluation harness: runs pipeline over golden songs and scores outputs.
Vault refs:
  - 01-LLM-Foundations/05-Evaluation-Guardrails.md
  - 05-Production-Systems/05-CI-Evals-Release.md

Run:
    python -m tests.eval_runner
"""
from __future__ import annotations

import json
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden_songs.json"


def chord_accuracy(predicted: list[str], expected: list[str]) -> float:
    """% of expected chords present in the same order in predicted (Levenshtein-ish)."""
    if not expected:
        return 1.0
    # TODO(Module 1, Lesson 5): implement proper sequence alignment
    matches = sum(1 for c in expected if c in predicted)
    return matches / len(expected)


def key_correct(predicted: str, expected: str) -> bool:
    return predicted.strip().lower() == expected.strip().lower()


def tempo_within(predicted: float, expected: float, tol_bpm: float = 5.0) -> bool:
    return abs(predicted - expected) <= tol_bpm


def run_eval():
    data = json.loads(GOLDEN.read_text())
    results = []
    for song in data["songs"]:
        # TODO(Module 5, Lesson 5):
        #   1. Run pipeline on an audio file for `song["id"]`
        #   2. Compute metrics (chord_accuracy, key_correct, tempo_within)
        #   3. Fail CI if aggregate metric drops below threshold
        print(f"[TODO] evaluate {song['title']}")
        results.append({"id": song["id"], "score": None})
    return results


if __name__ == "__main__":
    run_eval()
