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


def test_stems_node_keys_output_dir_on_job_id(monkeypatch, tmp_path):
    """stems_node must put stems under stems_dir/{job_id}/, derived from the
    job_id on state — NOT from splitting the (video-id-named) audio filename."""
    from backend.config import get_settings
    from backend.graph import nodes

    stems_dir = tmp_path / "stems"
    stems_dir.mkdir()

    settings = get_settings()
    monkeypatch.setattr(settings, "stems_dir", stems_dir, raising=False)
    monkeypatch.setattr(settings, "enable_stems", True, raising=False)

    # Audio file is named by video_id (the historical YouTube layout) to prove
    # we are NOT splitting the filename to find the job id.
    audio = tmp_path / "vid1234.mp3"
    audio.write_bytes(b"ID3fake")

    def _fake_separate(src, out_dir):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        produced = {}
        for name in ("vocals", "drums", "bass", "other"):
            p = out_dir / f"{name}.wav"
            p.write_bytes(b"RIFFfake")
            produced[name] = p
        return produced

    monkeypatch.setattr(
        "backend.ml.stem_separation.separate_stems", _fake_separate
    )

    state = {
        "job_id": "job-abc",
        "audio_path": str(audio),
    }
    out = nodes.stems_node(state)

    # Stems written under {job_id}, returned as relative-under-stems_dir paths.
    assert (stems_dir / "job-abc" / "vocals.wav").exists()
    assert out["stems"]["vocals"] == "job-abc/vocals.wav"
    # The video-id dir must NOT exist — proves we keyed on job_id.
    assert not (stems_dir / "vid1234").exists()


class TestServeEndpointsResolveYouTubeJob:
    """Given the post-3.2/3.3 on-disk layout for a YouTube job, the three serve
    endpoints must all resolve files under {job_id}."""

    @pytest.fixture
    def youtube_layout(self, monkeypatch, tmp_path):
        """Lay down the files an ingested YouTube job leaves on disk:
        uploads/{job_id}_{video_id}.mp3 and stems/{job_id}/{stem}.wav."""
        from backend.config import get_settings

        uploads = tmp_path / "uploads"
        stems = tmp_path / "stems"
        uploads.mkdir()
        (stems / "job-abc").mkdir(parents=True)

        (uploads / "job-abc_vid1234.mp3").write_bytes(b"ID3fake-mp3")
        for name in ("vocals", "drums", "bass", "other"):
            (stems / "job-abc" / f"{name}.wav").write_bytes(b"RIFFfake")

        settings = get_settings()
        monkeypatch.setattr(settings, "audio_upload_dir", uploads, raising=False)
        monkeypatch.setattr(settings, "stems_dir", stems, raising=False)
        return {"job_id": "job-abc", "uploads": uploads, "stems": stems}

    def test_serve_audio_resolves_youtube_job(self, api_client, youtube_layout):
        r = api_client.get("/api/v1/audio/job-abc")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "audio/mpeg"

    def test_serve_stem_resolves_youtube_job(self, api_client, youtube_layout):
        r = api_client.get("/api/v1/stems/job-abc/vocals")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "audio/wav"

    def test_export_midi_full_finds_youtube_audio(
        self, api_client, youtube_layout, monkeypatch
    ):
        """export_midi(stem='full') globs uploads/{job_id}* for the source —
        prove it picks up the {job_id}_{video_id}.mp3 file. Stub the actual
        transcription so the test stays hermetic."""

        def _fake_transcribe(source, out_midi):
            from pathlib import Path

            Path(out_midi).write_bytes(b"MThd-fake-midi")
            return out_midi

        monkeypatch.setattr(
            "backend.ml.midi_transcription.transcribe_to_midi", _fake_transcribe
        )
        r = api_client.get("/api/v1/midi/job-abc/full")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "audio/midi"
