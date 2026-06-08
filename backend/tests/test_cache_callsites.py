"""Call sites awaiting the now-async cache (Group 4 step c).

Uses the api_client + mock_mongo fixtures from conftest and a patched
async cache so /search and /lyrics round-trip without a real Redis.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def async_cache_patch():
    """Patch backend.main.cache.get/set with AsyncMocks."""
    store: dict[str, str] = {}

    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, value, ttl_seconds=1800):
        store[key] = value
        return True

    with (
        patch("backend.main.cache.get", new=AsyncMock(side_effect=fake_get)) as g,
        patch("backend.main.cache.set", new=AsyncMock(side_effect=fake_set)) as s,
    ):
        yield g, s, store


def test_search_awaits_cache(api_client, async_cache_patch):
    get_mock, set_mock, store = async_cache_patch
    with patch("backend.search.merged_search", new=AsyncMock(return_value=[{"title": "X"}])):
        resp = api_client.get("/api/v1/search?q=test&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cached"] is False
    assert body["results"] == [{"title": "X"}]
    # The result was awaited into the cache (proves cache.set was awaited).
    get_mock.assert_awaited()
    set_mock.assert_awaited()


def test_lyrics_awaits_cache(api_client, async_cache_patch):
    get_mock, set_mock, store = async_cache_patch
    payload = {"synced_lyrics": "[00:01]hi", "plain_lyrics": "hi", "source": "lrclib"}
    with patch("backend.lyrics.fetch_lyrics", new=AsyncMock(return_value=payload)):
        resp = api_client.get("/api/v1/lyrics?track_name=Hey&artist_name=Band")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cached"] is False
    assert body["source"] == "lrclib"
    get_mock.assert_awaited()
    set_mock.assert_awaited()
