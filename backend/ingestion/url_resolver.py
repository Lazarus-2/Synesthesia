"""Classify a submitted URL into a platform-specific extractor branch.

Single dispatch point used by both ``backend/main.py`` (edge validation —
to return a 400 with a precise platform name) and ``backend/graph/nodes.py``
``ingest_node`` (to route to the right extractor).

YouTube + YouTube Music both go through yt-dlp; Spotify is metadata-first
with an optional env-gated yt-dlp resolve. Everything else is rejected
upstream by the SSRF + host allowlist guard.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import parse_qs, urlparse

Platform = Literal["youtube", "youtube_music", "spotify", "unknown"]

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
}
_YOUTUBE_MUSIC_HOSTS = {"music.youtube.com"}
_SPOTIFY_HOSTS = {"open.spotify.com", "embed.spotify.com"}


def classify_url(url: str) -> Platform:
    """Return the platform name for a submitted URL.

    Handles the ``spotify:track:ID`` URI scheme too — that's the canonical
    deep-link shape on iOS/desktop and shows up in user pastes more often
    than the docs suggest.
    """
    if url.startswith("spotify:"):
        return "spotify"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in _YOUTUBE_MUSIC_HOSTS:
        return "youtube_music"
    if host in _YOUTUBE_HOSTS:
        return "youtube"
    if host in _SPOTIFY_HOSTS:
        return "spotify"
    return "unknown"


def normalize_to_www_youtube(url: str) -> str:
    """Rewrite ``music.youtube.com`` URLs to ``www.youtube.com`` so yt-dlp's
    ``web`` and ``web_safari`` clients can extract them without the
    music-subdomain PO token gymnastics.

    yt-dlp's ``web_music`` client supports ``music.youtube.com`` natively
    but requires a freshly-minted ``po_token`` per session (see
    https://github.com/yt-dlp/yt-dlp/wiki/Extractors#po-token-guide).
    Normalizing the host sidesteps that — the same underlying video is
    accessible from the regular ``www.youtube.com/watch?v=…`` URL.
    """
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() == "music.youtube.com":
        return parsed._replace(netloc="www.youtube.com").geturl()
    return url


def youtube_search_query(url: str) -> str | None:
    """Return the search terms from a ``youtube.com/results?search_query=...`` URL.

    The search-songs flow (and the "search YouTube" paste path) sends a
    results-page URL, which yt-dlp cannot download (it's a non-downloadable
    tab/playlist → "This playlist type is unviewable"). ``ingest_node``
    converts the extracted query into a ``ytsearch1:<query>`` target so
    yt-dlp searches YouTube and grabs the top video. Returns ``None`` for a
    normal watch/share URL (left untouched).
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS or parsed.path.rstrip("/") != "/results":
        return None
    query = parse_qs(parsed.query).get("search_query", [""])[0].strip()
    return query or None
