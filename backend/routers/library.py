"""Library listing (Plan 3 A7)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.auth import UserPrincipal, current_user
from backend.database import get_mongodb

router = APIRouter()


class LibraryEntry(BaseModel):
    """Summary row for the library page (Plan 3 A7)."""

    job_id: str
    title: str | None = None
    artist: str | None = None
    key: str
    tempo: float
    duration: float
    created_at: datetime | None = None
    vibe_palette: list[str] = []


class LibraryResponse(BaseModel):
    items: list[LibraryEntry]
    total: int
    limit: int
    offset: int


@router.get("/library", response_model=LibraryResponse)
async def list_library(
    limit: int = 24,
    offset: int = 0,
    principal: UserPrincipal | None = Depends(current_user),
    db=Depends(get_mongodb),
) -> LibraryResponse:
    """List previously-analyzed songs (Plan 3 A7), newest first.

    Identity comes from the JWT, never the query string (a client-supplied
    ``user_id`` could otherwise enumerate another user's library — BOLA). When
    a user is authenticated we filter to analyses they own; in anonymous mode
    (no principal, ``require_auth=False``) we surface the shared collection,
    matching single-tenant local use.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    projection = {
        "_id": 1,
        "title": 1,
        "artist": 1,
        "key": 1,
        "tempo": 1,
        "duration": 1,
        "created_at": 1,
        "vibe_palette": 1,
    }
    query: dict = {}
    if principal is not None:
        # Authenticated: only this user's analyses. (Anonymous mode leaves the
        # query open so a local single-tenant deployment still lists everything.)
        query["user_id"] = principal.user_id
    total = await db.song_analyses.count_documents(query)
    cursor = (
        db.song_analyses.find(query, projection).sort("created_at", -1).skip(offset).limit(limit)
    )
    items: list[LibraryEntry] = []
    async for doc in cursor:
        items.append(
            LibraryEntry(
                job_id=doc["_id"],
                title=doc.get("title"),
                artist=doc.get("artist"),
                key=doc.get("key", "Unknown"),
                tempo=float(doc.get("tempo", 0.0)),
                duration=float(doc.get("duration", 0.0)),
                created_at=doc.get("created_at"),
                vibe_palette=doc.get("vibe_palette") or [],
            )
        )
    return LibraryResponse(items=items, total=total, limit=limit, offset=offset)
