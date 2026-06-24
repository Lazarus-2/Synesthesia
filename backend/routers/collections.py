"""Collections & setlists (feat/collections-setlists).

A single ``collections`` Mongo collection holds both kinds, discriminated by
``kind``. Every endpoint requires auth; the ownership rule is 404 for missing
or unowned (never 403 — don't confirm another user's collection exists).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.auth import UserPrincipal, require_user
from backend.config import get_settings
from backend.database import get_mongodb
from backend.ratelimit import limiter
from backend.repositories import CollectionRepo
from backend.schemas import (
    AddSongRequest,
    CollectionCreateRequest,
    CollectionUpdateRequest,
)

router = APIRouter()


@router.post("/collections")
@limiter.limit(lambda: get_settings().collection_rate_limit)
async def create_collection(
    request: Request,
    req: CollectionCreateRequest,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """Create a collection or ordered setlist owned by the caller."""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name must not be empty")
    repo = CollectionRepo(db)
    cid = uuid.uuid4().hex
    created_at = datetime.now(UTC)
    doc = {
        "_id": cid,
        "user_id": principal.user_id,
        "name": name,
        "kind": req.kind,
        "description": req.description,
        "song_ids": req.song_ids,
        "created_at": created_at,
    }
    await repo.save(cid, doc)
    return {"id": cid, "created_at": created_at}


@router.get("/collections")
@limiter.limit(lambda: get_settings().collection_rate_limit)
async def list_collections(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """List the caller's collections/setlists, newest first."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    repo = CollectionRepo(db)
    docs, total = await repo.list_owned(principal.user_id, skip=offset, limit=limit)
    items = [
        {
            "id": d["_id"],
            "name": d.get("name"),
            "kind": d.get("kind", "collection"),
            "description": d.get("description"),
            "song_count": len(d.get("song_ids", [])),
            "created_at": d.get("created_at"),
        }
        for d in docs
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/collections/{cid}")
@limiter.limit(lambda: get_settings().collection_rate_limit)
async def get_collection(
    request: Request,
    cid: str,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """Return a collection with its songs hydrated in ``song_ids`` order.

    Songs the caller can't read (owned by another user) are filtered out, and
    ids with no matching analysis are skipped — but ``song_ids`` is returned
    verbatim so the client can tell which entries dropped.
    """
    repo = CollectionRepo(db)
    doc = await repo.get_owned(cid, principal.user_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    ids = doc.get("song_ids", [])
    by_id: dict[str, dict] = {}
    if ids:
        projection = {
            "_id": 1,
            "title": 1,
            "artist": 1,
            "key": 1,
            "tempo": 1,
            "duration": 1,
            "user_id": 1,
        }
        cursor = db.song_analyses.find({"_id": {"$in": ids}}, projection)
        async for s in cursor:
            owner = s.get("user_id")
            if owner is None or owner == principal.user_id:
                by_id[s["_id"]] = s

    songs = []
    for sid in ids:
        s = by_id.get(sid)
        if s is None:
            continue
        songs.append(
            {
                "job_id": sid,
                "title": s.get("title"),
                "artist": s.get("artist"),
                "key": s.get("key"),
                "tempo": s.get("tempo"),
                "duration": s.get("duration"),
            }
        )

    return {
        "id": doc["_id"],
        "name": doc.get("name"),
        "kind": doc.get("kind", "collection"),
        "description": doc.get("description"),
        "song_ids": ids,
        "songs": songs,
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


@router.put("/collections/{cid}")
@limiter.limit(lambda: get_settings().collection_rate_limit)
async def update_collection(
    request: Request,
    cid: str,
    req: CollectionUpdateRequest,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """Update the provided (non-None) fields of a collection the caller owns."""
    fields: dict[str, Any] = {}
    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name must not be empty")
        fields["name"] = name
    if req.description is not None:
        fields["description"] = req.description
    if req.song_ids is not None:
        fields["song_ids"] = req.song_ids
    repo = CollectionRepo(db)
    ok = await repo.update(cid, principal.user_id, fields)
    if not ok:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"updated": True}


@router.delete("/collections/{cid}")
@limiter.limit(lambda: get_settings().collection_rate_limit)
async def delete_collection(
    request: Request,
    cid: str,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """Delete a collection the caller owns."""
    repo = CollectionRepo(db)
    ok = await repo.delete(cid, principal.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"deleted": True}


@router.post("/collections/{cid}/songs")
@limiter.limit(lambda: get_settings().collection_rate_limit)
async def add_song_to_collection(
    request: Request,
    cid: str,
    req: AddSongRequest,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """Append a song (by job_id) to a collection the caller owns (idempotent)."""
    repo = CollectionRepo(db)
    ok = await repo.add_song(cid, principal.user_id, req.job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"added": True}


@router.delete("/collections/{cid}/songs/{job_id}")
@limiter.limit(lambda: get_settings().collection_rate_limit)
async def remove_song_from_collection(
    request: Request,
    cid: str,
    job_id: str,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """Remove a song from a collection the caller owns."""
    repo = CollectionRepo(db)
    ok = await repo.remove_song(cid, principal.user_id, job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"removed": True}
