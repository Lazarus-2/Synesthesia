"""Cross-platform search (Plan v2 C5) and synced lyrics (Plan v2 C6)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.ratelimit import limiter
from backend.services.cache import cache

router = APIRouter()


@router.get("/search")
@limiter.limit("30/minute")
async def search_tracks(request: Request, q: str, limit: int = 10) -> dict:
    """Search the merged Deezer + MusicBrainz catalog.

    Returns ``{results: [...]}`` where each entry has at minimum
    ``title``, ``artist``, plus whichever of ``deezer_id``, ``mbid``,
    ``preview_url``, ``image_url``, ``album``, ``year`` were resolved.

    Deezer (no auth, rich metadata) + MusicBrainz (rate-limited 1/sec,
    authoritative MBIDs) run in parallel. Merged and deduped by
    ``(title.lower, artist.lower)``.

    Cached for 1h via HybridCache — search queries are stable, and
    the upstream APIs (especially MusicBrainz) have aggressive rate
    limits we should respect.
    """
    if not q or len(q) > 200:
        raise HTTPException(status_code=400, detail="Query must be 1-200 characters")
    limit = max(1, min(limit, 25))

    import json as _json

    from backend.search import merged_search

    cache_key = f"search:q={q.lower().strip()}:limit={limit}"
    cached = await cache.get(cache_key)
    if cached:
        return {"results": _json.loads(cached), "cached": True}
    results = await merged_search(q, limit=limit)
    await cache.set(cache_key, _json.dumps(results), ttl_seconds=3600)
    return {"results": results, "cached": False}


@router.get("/lyrics")
@limiter.limit("60/minute")
async def get_lyrics(
    request: Request,
    track_name: str,
    artist_name: str,
    duration: int | None = None,
) -> dict:
    """Fetch synced + plain lyrics from LRCLIB.

    Returns ``{synced_lyrics, plain_lyrics, source}``. Both lyric
    fields are empty strings on a no-match — the frontend interprets
    that as "no lyrics available for this track".

    ``duration`` (seconds) is optional but helps LRCLIB disambiguate
    covers and live versions.
    """
    if not track_name or not artist_name:
        raise HTTPException(status_code=400, detail="track_name and artist_name are required")

    import json as _json

    from backend.lyrics import fetch_lyrics

    cache_key = (
        f"lyrics:t={track_name.lower().strip()}"
        f":a={artist_name.lower().strip()}:d={duration or 'any'}"
    )
    cached = await cache.get(cache_key)
    if cached:
        return _json.loads(cached) | {"cached": True}
    payload = await fetch_lyrics(track_name, artist_name, duration)
    # Cache hits AND misses (both are valuable). 6h TTL.
    await cache.set(cache_key, _json.dumps(payload), ttl_seconds=6 * 3600)
    return payload | {"cached": False}
