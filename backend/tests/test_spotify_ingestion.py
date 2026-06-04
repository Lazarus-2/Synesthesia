"""Unit tests for backend.ingestion.spotify.

Tests cover the URL parser exhaustively (every shape — URI, web, intl,
embed) and the metadata/fallback paths via mocks so we never hit the
live Spotify API.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.ingestion import spotify

# 22-char base62 Spotify track ID
_FAKE_ID = "3n3Ppam7vgaVa1iaRUc9Lp"


@pytest.mark.parametrize(
    "url",
    [
        f"spotify:track:{_FAKE_ID}",
        f"https://open.spotify.com/track/{_FAKE_ID}",
        f"https://open.spotify.com/track/{_FAKE_ID}?si=abc123",
        f"https://open.spotify.com/intl-en/track/{_FAKE_ID}",
        f"https://open.spotify.com/intl-de/track/{_FAKE_ID}?si=xyz",
        f"https://embed.spotify.com/track/{_FAKE_ID}",
    ],
)
def test_parse_spotify_url_handles_every_shape(url):
    assert spotify.parse_spotify_url(url) == _FAKE_ID


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://open.spotify.com/album/" + _FAKE_ID,
        "spotify:album:" + _FAKE_ID,
        "garbage",
        "",
    ],
)
def test_parse_spotify_url_rejects_non_track_urls(url):
    assert spotify.parse_spotify_url(url) is None


def test_fetch_metadata_returns_none_without_creds(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    assert spotify.fetch_spotify_metadata(_FAKE_ID) is None


def test_fetch_metadata_happy_path(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "x")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "y")
    fake_track = {
        "name": "Blackbird",
        "artists": [{"name": "The Beatles"}],
        "album": {
            "name": "The Beatles (White Album)",
            "release_date": "1968-11-22",
            "images": [{"url": "https://i.scdn.co/image/abc"}],
        },
        "external_ids": {"isrc": "GBAYE0500036"},
    }
    fake_client = MagicMock()
    fake_client.track.return_value = fake_track
    with (
        patch("spotipy.Spotify", return_value=fake_client),
        patch("spotipy.oauth2.SpotifyClientCredentials"),
    ):
        got = spotify.fetch_spotify_metadata(_FAKE_ID)
    assert got == {
        "spotify_id": _FAKE_ID,
        "title": "Blackbird",
        "artist": "The Beatles",
        "album": "The Beatles (White Album)",
        "year": "1968",
        "isrc": "GBAYE0500036",
        "album_art_url": "https://i.scdn.co/image/abc",
    }


def test_resolve_via_youtube_returns_none_without_env_flag(monkeypatch):
    monkeypatch.delenv("SPOTIFY_ALLOW_YTDLP_FALLBACK", raising=False)
    assert spotify.resolve_via_youtube("Blackbird", "The Beatles") is None


def test_resolve_via_youtube_returns_none_when_flag_false(monkeypatch):
    monkeypatch.setenv("SPOTIFY_ALLOW_YTDLP_FALLBACK", "false")
    assert spotify.resolve_via_youtube("Blackbird", "The Beatles") is None


def test_resolve_via_youtube_returns_top_match_url(monkeypatch):
    monkeypatch.setenv("SPOTIFY_ALLOW_YTDLP_FALLBACK", "true")
    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value = fake_ydl
    fake_ydl.extract_info.return_value = {
        "entries": [{"webpage_url": "https://www.youtube.com/watch?v=top"}]
    }
    with patch("yt_dlp.YoutubeDL", return_value=fake_ydl):
        got = spotify.resolve_via_youtube("Blackbird", "The Beatles")
    assert got == "https://www.youtube.com/watch?v=top"


def test_warn_if_fallback_enabled_only_logs_when_true(monkeypatch, caplog):
    import logging

    monkeypatch.delenv("SPOTIFY_ALLOW_YTDLP_FALLBACK", raising=False)
    with caplog.at_level(logging.WARNING, logger="backend.ingestion.spotify"):
        spotify.warn_if_fallback_enabled()
    assert "SPOTIFY_ALLOW_YTDLP_FALLBACK" not in caplog.text

    caplog.clear()
    monkeypatch.setenv("SPOTIFY_ALLOW_YTDLP_FALLBACK", "true")
    with caplog.at_level(logging.WARNING, logger="backend.ingestion.spotify"):
        spotify.warn_if_fallback_enabled()
    assert "SPOTIFY_ALLOW_YTDLP_FALLBACK=true" in caplog.text
