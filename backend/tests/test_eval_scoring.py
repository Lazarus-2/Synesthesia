"""Phase 4 G6 — quality-aware chord scoring for the golden-songs eval.

The old exact-string SequenceMatcher zeroed out a prediction like ``C7``
against an expected ``C`` even though the root (the hard part) was right.
Roots and qualities are now scored separately (0.7 / 0.3).
"""

from __future__ import annotations

import pytest

from backend.tests.eval_runner import chord_accuracy


class TestQualityAwareChordAccuracy:
    def test_exact_match_is_perfect(self):
        assert chord_accuracy(["C", "Am", "F", "G"], ["C", "Am", "F", "G"]) == pytest.approx(1.0)

    def test_empty_expected_is_perfect(self):
        assert chord_accuracy(["C"], []) == 1.0

    def test_richer_quality_keeps_root_credit(self):
        # The detector now emits 7ths; expected goldens are triads. Root
        # accuracy must survive — only the quality fraction is lost.
        score = chord_accuracy(["C7", "Am7", "F", "G7"], ["C", "Am", "F", "G"])
        assert score >= 0.7  # full root credit, partial quality credit

    def test_quality_match_beats_quality_mismatch(self):
        better = chord_accuracy(["C", "Am"], ["C", "Am"])
        worse = chord_accuracy(["C7", "Am7"], ["C", "Am"])
        assert better > worse

    def test_wrong_roots_score_low(self):
        score = chord_accuracy(["D", "Em", "G", "A"], ["C", "Am", "F", "G"])
        assert score < 0.4

    def test_totally_empty_prediction_scores_zero(self):
        assert chord_accuracy([], ["C", "Am"]) == pytest.approx(0.0)
