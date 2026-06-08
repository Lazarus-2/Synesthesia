"""FT-02 regression tests: YouTube-sourced audio/stems/MIDI resolve under
{job_id} rather than the yt-dlp video_id.

These tests are hermetic — yt-dlp, demucs and the ML registry are never
invoked. We monkeypatch the download boundary and assert on file naming /
state threading only.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_ingest_renames_youtube_download_to_job_id(monkeypatch, tmp_path):
    """A YouTube job must land at {job_id}_{video_id}.mp3 under uploads so the
    serve_audio glob ``{job_id}*`` resolves it."""
    from backend.graph import nodes

    uploads = tmp_path / "uploads"
    uploads.mkdir()

    # Stand in for the real yt-dlp ``YoutubeDL`` context manager. extract_info
    # writes the file yt-dlp would have produced (named by video_id) and
    # returns the matching info dict.
    class _FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            # yt-dlp's outtmpl resolves %(id)s → the video id; we honour that.
            (uploads / "vid1234.mp3").write_bytes(b"ID3fake-mp3-bytes")
            return {"id": "vid1234", "title": "Song", "uploader": "Artist"}

    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYDL)
    # Force the download dir to our tmp path (ingest_node hard-codes
    # ./storage/uploads otherwise).
    monkeypatch.setattr(nodes.Path, "mkdir", lambda self, **kw: None, raising=False)
    monkeypatch.setenv("FT02_UPLOAD_DIR", str(uploads))

    state = {
        "job_id": "job-abc",
        "youtube_url": "https://www.youtube.com/watch?v=vid1234",
        "instrument": "guitar",
        "difficulty": "beginner",
        "errors": [],
    }
    # Skip the real SSRF DNS resolution.
    monkeypatch.setattr(nodes, "_validate_youtube_url", lambda url: None)

    out = nodes.ingest_node(state)

    audio_path = Path(out["audio_path"])
    assert audio_path.name == "job-abc_vid1234.mp3"
    assert audio_path.exists()
    # serve_audio resolves by globbing job_id*; prove that glob hits.
    assert list(uploads.glob("job-abc*")) == [audio_path]


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
