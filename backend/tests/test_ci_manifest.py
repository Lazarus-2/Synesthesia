"""Guard: CI must run the full backend suite incl. the new chat tests (spec §11).

A regression where the workflow hard-codes a 2-file subset silently drops the
eval/regression coverage. This test fails if the workflow doesn't invoke the
whole tests dir (or doesn't name the new chat eval files).
"""

from __future__ import annotations

from pathlib import Path

_WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "test.yml"


def test_workflow_runs_full_backend_suite():
    text = _WF.read_text()
    # Accept any form that runs the whole tests directory:
    #   pytest ... backend/tests      (folder arg, possibly on the next line of a >- block)
    #   pytest tests                  (from inside backend/ working-directory)
    #   -m pytest                     (matrix-style invocation)
    runs_all = (
        "backend/tests" in text
        or "pytest tests" in text
        or "-m pytest" in text
    )
    assert runs_all, "CI must run the full backend test suite, not a 2-file subset"


def test_workflow_does_not_hardcode_two_file_subset():
    text = _WF.read_text()
    # The old smell: exactly two named files passed to pytest and nothing else.
    assert "test_tools.py test_chains.py" not in text
