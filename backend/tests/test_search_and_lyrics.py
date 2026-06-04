"""Unit tests for backend.search and backend.lyrics.

External APIs are mocked via httpx's MockTransport so tests stay
hermetic. We exercise the happy path, error fallback, and the
merged-dedupe logic across Deezer + MusicBrainz.
"""

from __future__ import annotations

import httpx
import pytest

from backend import lyrics, search


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _reset_mb_throttle():
    """Each test gets a fresh throttle window so we don't have to
    wait the 1s interval between tests."""
    search._mb_last_call_at = 0.0


# ---- Deezer ---------------------------------------------------------


@pytest.mark.asyncio
async def test_search_deezer_happy_path(monkeypatch):
    payload = {
        "data": [
            {
                "id": 123,
                "title": "Blackbird",
                "artist": {"name": "The Beatles"},
                "album": {"title": "The Beatles", "cover_medium": "https://e.cdn/x.jpg"},
                "duration": 138,
                "preview": "https://e.cdn/preview.mp3",
                "rank": 500000,
            }
        ]
    }

    def handler(request):
        assert request.url.path == "/search"
        return httpx.Response(200, json=payload)

    transport = _mock_transport(handler)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    monkeypatch.setattr("backend.search.httpx.AsyncClient", _Patched)
    got = await search.search_deezer("blackbird")
    assert len(got) == 1
    assert got[0]["source"] == "deezer"
    assert got[0]["title"] == "Blackbird"
    assert got[0]["artist"] == "The Beatles"
    assert got[0]["preview_url"] == "https://e.cdn/preview.mp3"


@pytest.mark.asyncio
async def test_search_deezer_returns_empty_on_http_error(monkeypatch):
    def handler(_request):
        return httpx.Response(503)

    transport = _mock_transport(handler)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    monkeypatch.setattr("backend.search.httpx.AsyncClient", _Patched)
    assert await search.search_deezer("blackbird") == []


# ---- MusicBrainz ----------------------------------------------------


@pytest.mark.asyncio
async def test_search_musicbrainz_happy_path(monkeypatch):
    payload = {
        "recordings": [
            {
                "id": "rec-mbid-1",
                "title": "Blackbird",
                "artist-credit": [{"name": "The Beatles"}],
                "releases": [{"title": "The Beatles", "date": "1968-11-22"}],
                "length": 138000,
                "score": 100,
            }
        ]
    }

    def handler(request):
        assert request.url.path == "/ws/2/recording"
        # MB requires a meaningful User-Agent — confirm we set it
        assert request.headers["User-Agent"].startswith("Synesthesia")
        return httpx.Response(200, json=payload)

    transport = _mock_transport(handler)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    monkeypatch.setattr("backend.search.httpx.AsyncClient", _Patched)
    got = await search.search_musicbrainz("blackbird")
    assert len(got) == 1
    assert got[0]["mbid"] == "rec-mbid-1"
    assert got[0]["year"] == "1968"
    assert got[0]["duration"] == 138


# ---- Merged dedupe --------------------------------------------------


@pytest.mark.asyncio
async def test_merged_search_dedupes_by_title_artist(monkeypatch):
    async def fake_deezer(q, limit=10):
        return [
            {
                "source": "deezer",
                "title": "Blackbird",
                "artist": "The Beatles",
                "image_url": "x.jpg",
            }
        ]

    async def fake_mb(q, limit=10):
        return [
            {
                "source": "musicbrainz",
                "title": "blackbird",
                "artist": "the beatles",
                "mbid": "abc",
                "year": "1968",
            }
        ]

    monkeypatch.setattr(search, "search_deezer", fake_deezer)
    monkeypatch.setattr(search, "search_musicbrainz", fake_mb)
    got = await search.merged_search("blackbird")
    assert len(got) == 1
    # Deezer entry survives (we layer MB onto it), gaining mbid + year
    assert got[0]["title"] == "Blackbird"
    assert got[0]["mbid"] == "abc"
    assert got[0]["year"] == "1968"
    assert got[0]["image_url"] == "x.jpg"


# ---- LRCLIB ---------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_lyrics_happy_path(monkeypatch):
    payload = {
        "syncedLyrics": "[00:01.00]hello\n[00:02.00]world",
        "plainLyrics": "hello\nworld",
    }

    def handler(request):
        assert "track_name" in request.url.params
        return httpx.Response(200, json=payload)

    transport = _mock_transport(handler)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    monkeypatch.setattr("backend.lyrics.httpx.AsyncClient", _Patched)
    got = await lyrics.fetch_lyrics("Blackbird", "The Beatles", duration=138)
    assert got == {
        "synced_lyrics": "[00:01.00]hello\n[00:02.00]world",
        "plain_lyrics": "hello\nworld",
        "source": "lrclib",
    }


@pytest.mark.asyncio
async def test_fetch_lyrics_returns_empty_strings_on_404(monkeypatch):
    def handler(_request):
        return httpx.Response(404, json={"error": "not found"})

    transport = _mock_transport(handler)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    monkeypatch.setattr("backend.lyrics.httpx.AsyncClient", _Patched)
    got = await lyrics.fetch_lyrics("not", "found")
    assert got == {"synced_lyrics": "", "plain_lyrics": "", "source": "lrclib"}


@pytest.mark.asyncio
async def test_fetch_lyrics_swallows_http_errors(monkeypatch):
    def handler(_request):
        return httpx.Response(503)

    transport = _mock_transport(handler)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = transport
            super().__init__(*a, **kw)

    monkeypatch.setattr("backend.lyrics.httpx.AsyncClient", _Patched)
    got = await lyrics.fetch_lyrics("x", "y")
    assert got == {"synced_lyrics": "", "plain_lyrics": "", "source": "lrclib"}
