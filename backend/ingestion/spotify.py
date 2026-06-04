"""Spotify URL ingestion — metadata-only by default, ToS-aware.

Why this is small and careful:

- Spotify's Web API audio-features and audio-analysis endpoints have
  been REMOVED for any app registered after Nov 2024 (and Feb 2026's
  changelog tightened things further). We use spotipy strictly for
  track metadata (title / artist / album / cover art / ISRC).
- Re-downloading Spotify content via yt-dlp lookup is arguably a ToS
  violation (Developer ToS §III.2.a.i). We gate that behind an
  explicit env flag ``SPOTIFY_ALLOW_YTDLP_FALLBACK=true`` and log a
  warning on startup so the operator knows what they enabled.
- The default ToS-clean playback path is the official Spotify iframe
  embed (``open.spotify.com/embed/track/{id}``). That's what the
  player UI renders when ``audio_source == "spotify_embed"``.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_TRACK_ID_RE = re.compile(
    r"""(?x)
    (?:
        spotify:track:                       # spotify URI
        | open\.spotify\.com/                # web URL
          (?:intl-[a-z-]+/)?                 #   optional ``intl-xx/`` locale prefix
          track/
        | embed\.spotify\.com/track/         # embed URL
    )
    (?P<id>[A-Za-z0-9]{22})                  # 22-char base62 track ID
    """
)


def parse_spotify_url(url: str) -> str | None:
    """Extract the 22-char Spotify track ID from any URL shape, or
    ``None`` if the input isn't a recognizable Spotify track reference.
    """
    m = _TRACK_ID_RE.search(url)
    return m.group("id") if m else None


def fetch_spotify_metadata(track_id: str) -> dict[str, Any] | None:
    """Fetch track metadata via spotipy client_credentials auth.

    Returns ``{title, artist, album, year, isrc, album_art_url, spotify_id}``
    on success, ``None`` if creds missing or API returned nothing.

    Requires ``SPOTIFY_CLIENT_ID`` + ``SPOTIFY_CLIENT_SECRET`` env vars
    (free; register a Dev Mode app at developer.spotify.com — note the
    Feb 2026 changes require a paid Premium subscription for the app
    owner, so this feature degrades gracefully when those creds aren't
    set).
    """
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not (client_id and client_secret):
        logger.debug("spotify.fetch: missing SPOTIFY_CLIENT_ID/SECRET; skipping")
        return None
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError:
        return None
    try:
        client = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        )
        track = client.track(track_id)
    except Exception as e:  # spotipy raises a flotilla of exception types
        logger.warning("spotify.fetch: API call failed: %s", e)
        return None
    if not track:
        return None
    images = track.get("album", {}).get("images") or []
    return {
        "spotify_id": track_id,
        "title": track.get("name") or "",
        "artist": ", ".join(a["name"] for a in track.get("artists") or []),
        "album": (track.get("album") or {}).get("name") or "",
        "year": ((track.get("album") or {}).get("release_date") or "")[:4],
        "isrc": ((track.get("external_ids") or {}).get("isrc")) or "",
        "album_art_url": images[0]["url"] if images else "",
    }


def resolve_via_youtube(title: str, artist: str) -> str | None:
    """Look up ``"{title} {artist}"`` on YouTube via yt-dlp's ``ytsearch1:``
    and return the resulting video URL.

    **ToS warning**: bridging Spotify metadata to a YouTube re-download
    is arguably circumvention of Spotify's content licensing. This
    function only runs when ``SPOTIFY_ALLOW_YTDLP_FALLBACK=true`` is
    explicitly set in env; calling it otherwise returns None.
    """
    if os.environ.get("SPOTIFY_ALLOW_YTDLP_FALLBACK", "").lower() != "true":
        return None
    try:
        import yt_dlp
    except ImportError:
        return None
    query = f"ytsearch1:{title} {artist}"
    try:
        with yt_dlp.YoutubeDL(
            {"quiet": True, "skip_download": True, "default_search": "ytsearch1"}
        ) as ydl:
            info = ydl.extract_info(query, download=False)
    except Exception as e:
        logger.warning("spotify.resolve_via_youtube: search failed: %s", e)
        return None
    # ytsearch1 wraps results under entries[0]
    entries = info.get("entries") if info else None
    if not entries:
        return None
    return entries[0].get("webpage_url") or entries[0].get("url")


def warn_if_fallback_enabled() -> None:
    """Emit a single startup warning so operators know the env flag is
    live. Called from main.py lifespan."""
    if os.environ.get("SPOTIFY_ALLOW_YTDLP_FALLBACK", "").lower() == "true":
        logger.warning(
            "SPOTIFY_ALLOW_YTDLP_FALLBACK=true is set — Spotify URLs will "
            "trigger a YouTube re-download path. This is a Spotify Developer "
            "ToS gray area; you own the legal risk. Set the env var to any "
            "other value to disable (metadata-only + iframe embed is the "
            "default ToS-clean path)."
        )
