"""Cross-platform music search backed by Deezer + MusicBrainz.

We do NOT use Spotify Web API for search because:
- ``/audio-features`` and ``/audio-analysis`` were removed for new apps
  in Nov 2024.
- Feb 2026 capped search ``limit`` at 10 and removed ``popularity``,
  ``available_markets``, batch endpoints.
- New "Dev Mode" requires the app owner's paid Premium subscription,
  capped at 5 test users.

Deezer's public API needs no auth and returns rich track metadata
(title, artist, album, year, preview_url, cover art). MusicBrainz is
the canonical source of truth for MBIDs and is also free, just
strictly rate-limited.

Both fetches run concurrently via ``asyncio.gather`` and the merged
result is deduped by ``(title.lower(), artist.lower())``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEEZER_BASE = "https://api.deezer.com"
_MB_BASE = "https://musicbrainz.org/ws/2"
_MB_USER_AGENT = "Synesthesia/0.1 ( https://github.com/aekam93/synesthesia )"

# MusicBrainz rate limit is 1 req/sec per IP. We honour it in-process
# with a tiny token bucket; this only works correctly with one worker
# process — for a multi-worker deployment, move the limiter to Redis.
_MB_MIN_INTERVAL_S = 1.0
_mb_last_call_at = 0.0
_mb_lock = asyncio.Lock()


async def _mb_throttle() -> None:
    """Sleep until enough time has elapsed since the last MB call."""
    global _mb_last_call_at
    async with _mb_lock:
        elapsed = time.monotonic() - _mb_last_call_at
        if elapsed < _MB_MIN_INTERVAL_S:
            await asyncio.sleep(_MB_MIN_INTERVAL_S - elapsed)
        _mb_last_call_at = time.monotonic()


async def search_deezer(q: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search Deezer's catalog. No auth required."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            r = await client.get(f"{_DEEZER_BASE}/search", params={"q": q, "limit": limit})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("search_deezer: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for item in data.get("data", []):
        out.append(
            {
                "source": "deezer",
                "deezer_id": item.get("id"),
                "title": item.get("title") or "",
                "artist": (item.get("artist") or {}).get("name") or "",
                "album": (item.get("album") or {}).get("title") or "",
                "duration": item.get("duration") or 0,
                "preview_url": item.get("preview") or "",
                "image_url": (item.get("album") or {}).get("cover_medium") or "",
                "rank": item.get("rank") or 0,
            }
        )
    return out


async def search_musicbrainz(q: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search MusicBrainz for recordings. 1 req/sec rate limit honoured."""
    await _mb_throttle()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0), headers={"User-Agent": _MB_USER_AGENT}
        ) as client:
            r = await client.get(
                f"{_MB_BASE}/recording",
                params={"query": q, "limit": limit, "fmt": "json"},
            )
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("search_musicbrainz: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for rec in data.get("recordings", []):
        artists = rec.get("artist-credit") or []
        artist_name = " ".join(a.get("name", "") for a in artists if isinstance(a, dict)).strip()
        releases = rec.get("releases") or []
        album = releases[0].get("title", "") if releases else ""
        year = (releases[0].get("date", "")[:4]) if releases else ""
        out.append(
            {
                "source": "musicbrainz",
                "mbid": rec.get("id") or "",
                "title": rec.get("title") or "",
                "artist": artist_name,
                "album": album,
                "year": year,
                "duration": (rec.get("length") or 0) // 1000,  # ms -> s
                "score": rec.get("score") or 0,
            }
        )
    return out


def _dedupe_key(item: dict[str, Any]) -> tuple[str, str]:
    return (item.get("title", "").strip().lower(), item.get("artist", "").strip().lower())


async def merged_search(q: str, limit: int = 10) -> list[dict[str, Any]]:
    """Run both searches in parallel and merge.

    Dedupe key is ``(title.lower, artist.lower)``. When both sources
    have the same track, we merge their fields (Deezer's image_url +
    preview_url + MusicBrainz's MBID + year). Items appear in the
    order they were returned by the higher-confidence source.
    """
    deezer, mb = await asyncio.gather(
        search_deezer(q, limit=limit), search_musicbrainz(q, limit=limit)
    )
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    # Deezer first — usually richer metadata.
    for item in deezer:
        by_key[_dedupe_key(item)] = item
    # MusicBrainz layered on top — fills in mbid/year/album when missing.
    for item in mb:
        key = _dedupe_key(item)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = item
        else:
            for f in ("mbid", "year"):
                if not existing.get(f) and item.get(f):
                    existing[f] = item[f]
            existing["sources"] = sorted(
                {existing.get("source", ""), item.get("source", "")} - {""}
            )
    return list(by_key.values())[:limit]
