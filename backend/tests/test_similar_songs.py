"""Unit tests for backend.services.similar_songs.

All network calls mocked — never hits the real API.
"""
from __future__ import annotations

import httpx
import pytest

import backend.services.similar_songs as _ss_module  # import once; patch on it directly

# ---------------------------------------------------------------------------
# G4.1 — Last.fm happy-path parse
# ---------------------------------------------------------------------------

LASTFM_SIMILAR_PAYLOAD = {
    "similartracks": {
        "track": [
            {
                "name": "Hey Jude",
                "artist": {"name": "The Beatles"},
                "url": "https://www.last.fm/music/The+Beatles/_/Hey+Jude",
                "image": [
                    {"#text": "", "size": "small"},
                    {"#text": "https://img.lastfm/hey-jude.jpg", "size": "medium"},
                ],
                "match": "0.89",
            },
            {
                "name": "Let It Be",
                "artist": {"name": "The Beatles"},
                "url": "https://www.last.fm/music/The+Beatles/_/Let+It+Be",
                "image": [
                    {"#text": "", "size": "small"},
                    {"#text": "", "size": "medium"},
                ],
                "match": "0.77",
            },
        ]
    }
}


@pytest.mark.asyncio
async def test_fetch_similar_songs_lastfm_happy_path(monkeypatch):
    """Primary path: Last.fm track.getSimilar parses correctly into
    list[dict] with expected keys."""
    from backend.config import Settings
    monkeypatch.setattr(
        _ss_module, "get_settings",
        lambda: Settings.model_construct(lastfm_api_key="fake-key-123"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "ws.audioscrobbler.com"
        assert request.url.params["method"] == "track.getSimilar"
        assert request.url.params["track"] == "Blackbird"
        assert request.url.params["artist"] == "The Beatles"
        assert request.url.params["api_key"] == "fake-key-123"
        assert request.url.params["format"] == "json"
        return httpx.Response(200, json=LASTFM_SIMILAR_PAYLOAD)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(_ss_module, "httpx", type("httpx", (), {
        "AsyncClient": _Patched,
        "Timeout": httpx.Timeout,
        "HTTPError": httpx.HTTPError,
    })())

    async def _noop_get(k): return None
    async def _noop_set(*a, **kw): return True
    monkeypatch.setattr(_ss_module.cache, "get", _noop_get)
    monkeypatch.setattr(_ss_module.cache, "set", _noop_set)

    results = await _ss_module.fetch_similar_songs(
        "Blackbird", "The Beatles", limit=8
    )
    assert len(results) == 2
    first = results[0]
    assert first["title"] == "Hey Jude"
    assert first["artist"] == "The Beatles"
    assert first["url"] == "https://www.last.fm/music/The+Beatles/_/Hey+Jude"
    assert first["image"] == "https://img.lastfm/hey-jude.jpg"
    assert first["source"] == "lastfm"
    assert abs(float(first["match"]) - 0.89) < 1e-6
    # Second result: missing medium image falls back to ""
    assert results[1]["image"] == ""


# ---------------------------------------------------------------------------
# G4.2 — Graceful no-op when key absent → Deezer fallback fires
# (tests already committed; section marker retained for traceability)
# ---------------------------------------------------------------------------

DEEZER_ARTIST_SEARCH = {
    "data": [{"id": 27, "name": "The Beatles"}]
}
DEEZER_RELATED = {
    "data": [{"id": 99, "name": "Oasis"}]
}
DEEZER_TOP_TRACKS = {
    "data": [
        {
            "title": "Wonderwall",
            "artist": {"name": "Oasis"},
            "link": "https://www.deezer.com/track/1",
            "album": {"cover_medium": "https://cdn.deezer.com/oasis.jpg"},
        }
    ]
}


def _deezer_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/search/artist":
        return httpx.Response(200, json=DEEZER_ARTIST_SEARCH)
    if path == "/artist/27/related":
        return httpx.Response(200, json=DEEZER_RELATED)
    if path == "/artist/99/top":
        return httpx.Response(200, json=DEEZER_TOP_TRACKS)
    return httpx.Response(404, json={"error": "not found"})


@pytest.mark.asyncio
async def test_fetch_similar_songs_no_key_uses_deezer(monkeypatch):
    """When LASTFM_API_KEY is absent the function must NOT call Last.fm
    and must return results from the Deezer fallback path."""
    from backend.config import Settings
    monkeypatch.setattr(
        _ss_module, "get_settings",
        lambda: Settings.model_construct(lastfm_api_key=""),
    )
    # Reset warned flag so log-once guard doesn't suppress warning path.
    _ss_module._warned_no_key = False

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        assert request.url.host != "ws.audioscrobbler.com", (
            "Last.fm must NOT be called when API key is absent"
        )
        return _deezer_handler(request)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(_ss_module, "httpx", type("httpx", (), {
        "AsyncClient": _Patched,
        "Timeout": httpx.Timeout,
        "HTTPError": httpx.HTTPError,
    })())

    async def _noop_get(k): return None
    async def _noop_set(*a, **kw): return True
    monkeypatch.setattr(_ss_module.cache, "get", _noop_get)
    monkeypatch.setattr(_ss_module.cache, "set", _noop_set)

    results = await _ss_module.fetch_similar_songs("Come Together", "The Beatles", limit=8)
    assert len(results) >= 1
    assert all(r["source"] == "deezer" for r in results)
    assert results[0]["title"] == "Wonderwall"
    assert results[0]["artist"] == "Oasis"
    assert "ws.audioscrobbler.com" not in calls


# ---------------------------------------------------------------------------
# G4.3 — Empty/error responses return [] without raising
# (tests already committed; section marker retained for traceability)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_similar_songs_empty_lastfm_response(monkeypatch):
    """Empty track list from Last.fm → [] with no exception."""
    from backend.config import Settings
    monkeypatch.setattr(
        _ss_module, "get_settings",
        lambda: Settings.model_construct(lastfm_api_key="testkey"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "track.getSimilar" in str(request.url):
            return httpx.Response(200, json={"similartracks": {"track": []}})
        # artist.getSimilar fallback also empty
        return httpx.Response(200, json={"similarartists": {"artist": []}})

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(_ss_module, "httpx", type("httpx", (), {
        "AsyncClient": _Patched,
        "Timeout": httpx.Timeout,
        "HTTPError": httpx.HTTPError,
    })())

    async def _noop_get(k): return None
    async def _noop_set(*a, **kw): return True
    monkeypatch.setattr(_ss_module.cache, "get", _noop_get)
    monkeypatch.setattr(_ss_module.cache, "set", _noop_set)

    result = await _ss_module.fetch_similar_songs("Unknown Track", "NoArtist")
    assert result == []


@pytest.mark.asyncio
async def test_fetch_similar_songs_http_error_returns_empty(monkeypatch):
    """HTTP 503 from Last.fm must not raise — returns []."""
    from backend.config import Settings
    monkeypatch.setattr(
        _ss_module, "get_settings",
        lambda: Settings.model_construct(lastfm_api_key="testkey"),
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    class _Patched(httpx.AsyncClient):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(_ss_module, "httpx", type("httpx", (), {
        "AsyncClient": _Patched,
        "Timeout": httpx.Timeout,
        "HTTPError": httpx.HTTPError,
    })())

    async def _noop_get(k): return None
    async def _noop_set(*a, **kw): return True
    monkeypatch.setattr(_ss_module.cache, "get", _noop_get)
    monkeypatch.setattr(_ss_module.cache, "set", _noop_set)

    result = await _ss_module.fetch_similar_songs("Blackbird", "The Beatles")
    assert result == []
