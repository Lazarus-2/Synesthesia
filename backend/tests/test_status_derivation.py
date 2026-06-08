"""Top-level status derivation at fan-in.

``derive_status`` maps a merged AnalysisState into one of
"ok" | "degraded" | "failed":

  - "failed": feature extraction never produced usable analysis
    (no key / no chords) — the run is unusable.
  - "degraded": deterministic analysis succeeded but at least one fan-out
    node recorded an error (LLM down, demucs missing, etc.).
  - "ok": usable analysis and no recorded errors.
"""

from __future__ import annotations

from unittest.mock import patch

from backend.graph.state import NO_CHORDS_MESSAGE
from backend.graph.status import derive_status
from backend.schemas import ChordEvent


def _usable(**over):
    base = {
        "key": "C major",
        "chords": [ChordEvent(chord="C", start=0.0, end=1.0)],
        "errors": [],
        "feature_error": None,
    }
    base.update(over)
    return base


class TestDeriveStatus:
    def test_clean_run_is_ok(self):
        assert derive_status(_usable()) == "ok"

    def test_fanout_error_with_usable_analysis_is_degraded(self):
        state = _usable(errors=["theory: LLM commentary engine offline"])
        assert derive_status(state) == "degraded"

    def test_feature_extraction_failure_is_failed(self):
        state = {
            "errors": ["Feature extraction failed: decode error"],
            "feature_error": "Feature extraction failed: decode error",
            "chords": [],
        }
        assert derive_status(state) == "failed"

    def test_no_chords_is_failed_even_without_feature_error(self):
        # e.g. ingest/validate rejected the input upstream.
        assert derive_status({"errors": ["Rejected URL"], "chords": []}) == "failed"

    def test_recovered_retry_is_ok_despite_stale_errors_log(self):
        """FT-01 at the fan-in: feature_error cleared + usable chords => not
        failed, even though the append-only errors log still holds the prior
        feature failure string."""
        state = _usable(
            errors=["Feature extraction failed: transient decode error"],
            feature_error=None,
        )
        # A stale *feature* error in the log alone shouldn't downgrade a fully
        # recovered run that has no fan-out errors.
        assert derive_status(state) == "ok"

    # --- Fix 2 regression tests ---

    def test_no_chords_with_no_feature_error_is_failed(self):
        """Exact path from the review: features ran cleanly but chords is [].
        derive_status must still classify as 'failed' (policy unchanged)."""
        assert derive_status({"feature_error": None, "errors": [], "chords": []}) == "failed"

    def test_features_node_appends_actionable_message_when_no_chords(self):
        """After a clean extraction that yields zero chords, features_node must
        append NO_CHORDS_MESSAGE to errors so tasks.py can surface it instead
        of the bare 'Analysis failed' string."""
        from backend.graph.nodes import features_node

        # Stub all four ML calls: key/tempo succeed, beats succeed, but
        # chord detection returns [] (speech/silence/non-harmonic audio).
        with (
            patch("backend.ml.key_estimation.estimate_key_and_tempo", return_value=("C major", 120.0)),
            patch("backend.ml.beat_tracking.track_beats", return_value=[]),
            patch("backend.ml.chord_detection.detect_chords", return_value=[]),
            patch("backend.ml.structure_detection.detect_sections", return_value=[]),
        ):
            result = features_node({"audio_path": "/fake/audio.mp3", "retries": 0})

        assert result.get("feature_error") is None, "no-chords must NOT set feature_error"
        assert result.get("chords") == []
        errors = result.get("errors", [])
        assert any(NO_CHORDS_MESSAGE in e for e in errors), (
            f"Expected NO_CHORDS_MESSAGE in errors; got {errors!r}"
        )

    def test_no_chords_errors_log_is_non_empty_for_tasks(self):
        """Verify that '; '.join(errors) is non-empty when no chords are
        detected, so tasks.py shows the user an actionable reason rather than
        the bare fallback string 'Analysis failed'."""
        from backend.graph.nodes import features_node

        with (
            patch("backend.ml.key_estimation.estimate_key_and_tempo", return_value=("A minor", 90.0)),
            patch("backend.ml.beat_tracking.track_beats", return_value=[]),
            patch("backend.ml.chord_detection.detect_chords", return_value=[]),
            patch("backend.ml.structure_detection.detect_sections", return_value=[]),
        ):
            result = features_node({"audio_path": "/fake/audio.mp3", "retries": 0})

        errors = result.get("errors", [])
        assert "; ".join(errors), "errors must be non-empty so tasks.py can surface a reason"
