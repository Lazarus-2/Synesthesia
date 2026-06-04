"""LRCLIB synced-lyrics integration.

LRCLIB is the right answer for synced lyrics in 2026:
- ~3 million tracks in the catalog
- Returns ``syncedLyrics`` in LRC format (``[mm:ss.cc]line`` per line)
  plus a ``plainLyrics`` fallback
- No API key, no documented rate limit, no auth
- Public SQLite dumps if we ever want to mirror

API: ``GET https://lrclib.net/api/get?track_name=…&artist_name=…&duration=…``
Returns 404 when nothing matches; we surface that as a clean empty
result instead of a backend error.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://lrclib.net/api"


async def fetch_lyrics(
    track_name: str, artist_name: str, duration: int | None = None
) -> dict[str, Any]:
    """Return ``{synced_lyrics, plain_lyrics, source}`` for the closest
    match. Both lyric fields can be empty strings on a partial match
    or no match at all.

    ``duration`` (seconds) is optional but helps LRCLIB pick the right
    version when there are multiple recordings of the same song
    (covers / live versions / re-recordings).
    """
    params: dict[str, Any] = {"track_name": track_name, "artist_name": artist_name}
    if duration is not None:
        params["duration"] = int(duration)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            r = await client.get(f"{_BASE}/get", params=params)
        if r.status_code == 404:
            return {"synced_lyrics": "", "plain_lyrics": "", "source": "lrclib"}
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("fetch_lyrics: %s", e)
        return {"synced_lyrics": "", "plain_lyrics": "", "source": "lrclib"}
    return {
        "synced_lyrics": data.get("syncedLyrics") or "",
        "plain_lyrics": data.get("plainLyrics") or "",
        "source": "lrclib",
    }
