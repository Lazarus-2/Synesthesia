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
