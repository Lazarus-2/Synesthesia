"""Theory Lab — deterministic reharmonization."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.config import get_settings
from backend.ratelimit import limiter
from backend.schemas import ReharmonizeRequest
from backend.theory.reharmonize import reharmonize

router = APIRouter()


@router.post("/theory/reharmonize")
@limiter.limit(lambda: get_settings().theory_rate_limit)
async def theory_reharmonize(request: Request, req: ReharmonizeRequest) -> dict:
    """Deterministic reharmonization suggestions (Theory Lab).

    Stateless: no auth, no db. Returns ``{"suggestions": [...]}`` where each
    suggestion is ``{type, label, chord, explanation}``. ``request`` is required
    by the slowapi limiter (keys the rate limit by IP).
    """
    key = (req.key or "").strip()
    chord = (req.chord or "").strip()
    if not key or not chord:
        raise HTTPException(status_code=400, detail="key and chord are required")
    return {"suggestions": reharmonize(key, chord, req.next_chord)}
