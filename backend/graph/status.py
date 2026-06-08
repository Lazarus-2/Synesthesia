"""Derive the top-level run status from a merged AnalysisState (fan-in).

The LangGraph pipeline fans in to END, so this pure function runs in the
worker once ``graph.ainvoke`` returns. It is kept separate from the worker
so it can be unit-tested without Mongo/Taskiq.
"""

from __future__ import annotations

from typing import Literal

from backend.graph.state import FEATURE_ERROR_PREFIX, AnalysisState

# Alias kept local for readability; the canonical string lives in state.py so
# features_node and derive_status share exactly one definition.
_FEATURE_ERROR_MARKER = FEATURE_ERROR_PREFIX


def _has_usable_analysis(state: AnalysisState) -> bool:
    """A run is usable if features produced chords and the latest feature
    attempt did not fail."""
    if state.get("feature_error"):
        return False
    return bool(state.get("chords"))


def derive_status(state: AnalysisState) -> Literal["ok", "degraded", "failed"]:
    """Map the merged fan-in state to a top-level status.

    - "failed": no usable deterministic analysis (no chords, or the latest
      feature attempt failed).
    - "degraded": usable analysis, but at least one non-feature error was
      recorded by a fan-out node (theory/instrument/similarity/stems).
    - "ok": usable analysis and no fan-out errors.
    """
    if not _has_usable_analysis(state):
        return "failed"

    # Usable analysis: ignore stale *feature* errors (FT-01 recovered retry);
    # any remaining error is a fan-out degradation.
    fanout_errors = [
        e for e in state.get("errors", []) if _FEATURE_ERROR_MARKER not in e
    ]
    if fanout_errors:
        return "degraded"
    return "ok"
