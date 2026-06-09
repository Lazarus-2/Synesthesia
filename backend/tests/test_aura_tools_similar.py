"""Test find_similar_songs @tool uses the new online service, not similarity_chain."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeRepo:
    def __init__(self, doc):
        self._doc = doc

    async def get(self, job_id):
        return self._doc

    async def get_owned(self, job_id, uid):
        return self._doc


@pytest.mark.asyncio
async def test_find_similar_songs_tool_calls_new_service(monkeypatch):
    """find_similar_songs @tool must call fetch_similar_songs with the stored
    title+artist from the analysis document, NOT the old find_similar function."""
    captured: list[tuple] = []

    async def fake_fetch(title, artist, *, limit=8):
        captured.append((title, artist, limit))
        return [
            {
                "title": "Hey Jude",
                "artist": "The Beatles",
                "url": "https://www.last.fm/x",
                "image": "",
                "source": "lastfm",
                "match": 0.9,
            }
        ]

    monkeypatch.setattr(
        "backend.chains.aura_tools.fetch_similar_songs", fake_fetch
    )

    fake_doc = {
        "_id": "job-abc",
        "title": "Blackbird",
        "artist": "The Beatles",
        "chords": [{"chord": "G", "start": 0.0, "end": 1.0, "confidence": 1.0, "color": "#fff"}],
        "key": "G major",
    }

    monkeypatch.setattr(
        "backend.chains.aura_tools._resolve_analysis_repo",
        lambda: _FakeRepo(fake_doc),
    )
    # No user ownership check for this test
    import backend.chains.aura_tools as at
    at.current_user_id.set(None)

    result = await at.find_similar_songs.ainvoke({"analysis_job_id": "job-abc"})

    assert captured == [("Blackbird", "The Beatles", 8)]
    assert isinstance(result, list)
    assert result[0]["title"] == "Hey Jude"
    assert result[0]["source"] == "lastfm"


@pytest.mark.asyncio
async def test_find_similar_songs_tool_missing_analysis(monkeypatch):
    """Returns error dict when analysis not found (unchanged behavior)."""
    monkeypatch.setattr(
        "backend.chains.aura_tools._resolve_analysis_repo",
        lambda: _FakeRepo(None),
    )
    import backend.chains.aura_tools as at
    at.current_user_id.set(None)

    result = await at.find_similar_songs.ainvoke({"analysis_job_id": "no-such-job"})
    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.asyncio
async def test_find_similar_songs_tool_no_title_artist_uses_empty_string(monkeypatch):
    """A doc without title/artist still calls fetch_similar_songs with '' strings
    rather than crashing."""
    captured: list[tuple] = []

    async def fake_fetch(title, artist, *, limit=8):
        captured.append((title, artist, limit))
        return []

    monkeypatch.setattr("backend.chains.aura_tools.fetch_similar_songs", fake_fetch)

    fake_doc = {
        "_id": "job-xyz",
        "title": None,
        "artist": None,
        "chords": [],
        "key": None,
    }
    monkeypatch.setattr(
        "backend.chains.aura_tools._resolve_analysis_repo",
        lambda: _FakeRepo(fake_doc),
    )
    import backend.chains.aura_tools as at
    at.current_user_id.set(None)

    result = await at.find_similar_songs.ainvoke({"analysis_job_id": "job-xyz"})
    assert captured == [("", "", 8)]
    assert result == []
