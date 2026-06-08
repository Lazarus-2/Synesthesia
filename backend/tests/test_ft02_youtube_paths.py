"""FT-02 regression tests: YouTube-sourced audio/stems/MIDI resolve under
{job_id} rather than the yt-dlp video_id.

These tests are hermetic — yt-dlp, demucs and the ML registry are never
invoked. We monkeypatch the download boundary and assert on file naming /
state threading only.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_analysis_state_has_job_id_key():
    """job_id must be a declared input field so nodes can read it off state."""
    import typing

    from backend.graph.state import AnalysisState

    # __annotations__ is the authoritative field list for a TypedDict.
    assert "job_id" in AnalysisState.__annotations__
    # With ``from __future__ import annotations`` active (Python 3.12) the raw
    # __annotations__ dict contains ForwardRef objects, not bare types.  Use
    # get_type_hints() which resolves them so we can assert the concrete type.
    resolved = typing.get_type_hints(AnalysisState)
    assert resolved["job_id"] is str
