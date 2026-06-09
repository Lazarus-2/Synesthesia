"""Online similar-songs fetcher backed by Last.fm + Deezer fallback.

Primary:  Last.fm ``track.getSimilar`` (free, needs LASTFM_API_KEY).
Fallback: Deezer artist-search → top tracks (no auth).
Cache:    HybridCache with 6h TTL (mirrors lyrics caching).

Graceful no-op: when LASTFM_API_KEY is unset the function logs once and
falls through to Deezer.  This mirrors the AcoustID pattern in
``backend/ingestion/acoustid_enrich.py``.

Each result dict schema::

    {
        "title":  str,
        "artist": str,
        "url":    str | None,
        "image":  str | None,
        "source": "lastfm" | "deezer",
        "match":  float | None,   # Last.fm similarity score [0..1]
    }
"""
from __future__ import annotations

import json
import logging

import httpx

from backend.config import get_settings
from backend.services.cache import cache

logger = logging.getLogger(__name__)

_LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"
_DEEZER_BASE = "https://api.deezer.com"
_CACHE_TTL = 6 * 3600  # 6 hours, matching lyrics cache

# Warn once per process when the key is absent so operators notice.
_warned_no_key: bool = False


def _cache_key(title: str, artist: str, limit: int) -> str:
    return f"similar_songs:{title.lower()}:{artist.lower()}:{limit}"


async def _fetch_lastfm(
    title: str,
    artist: str,
    *,
    api_key: str,
    limit: int,
) -> list[dict]:
    """Call Last.fm track.getSimilar; fall back to artist.getSimilar on 4xx."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            r = await client.get(
                _LASTFM_BASE,
                params={
                    "method": "track.getSimilar",
                    "track": title,
                    "artist": artist,
                    "api_key": api_key,
                    "limit": limit,
                    "format": "json",
                    "autocorrect": "1",
                },
            )
        if r.status_code == 200:
            data = r.json()
            tracks = (data.get("similartracks") or {}).get("track") or []
            if tracks:
                return _parse_lastfm_tracks(tracks)

        # artist.getSimilar fallback — returns top artist tracks
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            r2 = await client.get(
                _LASTFM_BASE,
                params={
                    "method": "artist.getSimilar",
                    "artist": artist,
                    "api_key": api_key,
                    "limit": limit,
                    "format": "json",
                },
            )
        if r2.status_code == 200:
            data2 = r2.json()
            artists = (data2.get("similarartists") or {}).get("artist") or []
            return _parse_lastfm_artist_fallback(artists)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("similar_songs: Last.fm request failed: %s", exc)
    return []


def _parse_lastfm_tracks(tracks: list[dict]) -> list[dict]:
    out = []
    for t in tracks:
        images = t.get("image") or []
        # Prefer medium image; fall back to first non-empty
        medium = next(
            (img["#text"] for img in images if img.get("size") == "medium"),
            next((img["#text"] for img in images if img.get("#text")), ""),
        )
        out.append(
            {
                "title": t.get("name") or "",
                "artist": (t.get("artist") or {}).get("name") or "",
                "url": t.get("url") or None,
                "image": medium or "",
                "source": "lastfm",
                "match": float(t["match"]) if t.get("match") else None,
            }
        )
    return out


def _parse_lastfm_artist_fallback(artists: list[dict]) -> list[dict]:
    """Convert similar-artist records to the same result dict shape."""
    out = []
    for a in artists:
        images = a.get("image") or []
        medium = next(
            (img["#text"] for img in images if img.get("size") == "medium"),
            next((img["#text"] for img in images if img.get("#text")), ""),
        )
        out.append(
            {
                "title": "",
                "artist": a.get("name") or "",
                "url": a.get("url") or None,
                "image": medium or "",
                "source": "lastfm",
                "match": float(a["match"]) if a.get("match") else None,
            }
        )
    return out


async def _fetch_deezer_fallback(artist: str, *, limit: int) -> list[dict]:
    """Deezer: search for the artist → grab related artists → their top tracks."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            r = await client.get(
                f"{_DEEZER_BASE}/search/artist",
                params={"q": artist, "limit": 1},
            )
        r.raise_for_status()
        items = r.json().get("data") or []
        if not items:
            return []
        artist_id = items[0]["id"]

        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            r2 = await client.get(f"{_DEEZER_BASE}/artist/{artist_id}/related")
        r2.raise_for_status()
        related = r2.json().get("data") or []

        results: list[dict] = []
        for rel in related[:4]:
            rel_id = rel.get("id")
            if not rel_id:
                continue
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                    r3 = await client.get(
                        f"{_DEEZER_BASE}/artist/{rel_id}/top",
                        params={"limit": max(1, limit // 4)},
                    )
                r3.raise_for_status()
                for track in r3.json().get("data") or []:
                    results.append(
                        {
                            "title": track.get("title") or "",
                            "artist": (track.get("artist") or {}).get("name") or rel.get("name") or "",
                            "url": track.get("link") or None,
                            "image": (track.get("album") or {}).get("cover_medium") or "",
                            "source": "deezer",
                            "match": None,
                        }
                    )
            except (httpx.HTTPError, ValueError) as exc:
                logger.debug("similar_songs: deezer top-tracks failed for %s: %s", rel_id, exc)

        return results[:limit]
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("similar_songs: Deezer fallback failed: %s", exc)
        return []


async def fetch_similar_songs(
    title: str,
    artist: str,
    *,
    limit: int = 8,
) -> list[dict]:
    """Fetch similar songs from Last.fm (primary) or Deezer (fallback when
    LASTFM_API_KEY is unset).

    Results are cached for 6 h.  Returns [] on any failure so the analysis
    pipeline always degrades gracefully.
    """
    global _warned_no_key

    ck = _cache_key(title, artist, limit)
    cached = await cache.get(ck)
    if cached:
        try:
            return json.loads(cached)
        except (ValueError, TypeError):
            pass

    settings = get_settings()
    api_key = settings.lastfm_api_key

    results: list[dict] = []
    if api_key:
        results = await _fetch_lastfm(title, artist, api_key=api_key, limit=limit)
    else:
        if not _warned_no_key:
            logger.info(
                "similar_songs: LASTFM_API_KEY not set; using Deezer fallback. "
                "Set LASTFM_API_KEY for richer recommendations."
            )
            _warned_no_key = True
        results = await _fetch_deezer_fallback(artist, limit=limit)

    try:
        await cache.set(ck, json.dumps(results), ttl_seconds=_CACHE_TTL)
    except Exception as exc:
        logger.debug("similar_songs: cache write failed: %s", exc)

    return results
