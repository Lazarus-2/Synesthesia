"""User identity + personalization preferences (Plan 3 A8/G1/G3)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.auth import UserPrincipal, require_user
from backend.config import get_settings
from backend.database import get_mongodb
from backend.ratelimit import limiter

router = APIRouter()


class UserRequest(BaseModel):
    # Optional: identity is taken from the auth token (Phase 6 G1). When
    # present it must match the caller's own id, else the write is rejected.
    id: str | None = None
    username: str
    instrument: str = "guitar"
    difficulty: str = "beginner"


class UserPreferences(BaseModel):
    """Persistent personalization defaults (Plan 3 A8)."""

    default_instrument: str | None = None
    default_difficulty: str | None = None
    default_capo: int | None = None


@router.post("/user")
@limiter.limit(lambda: get_settings().user_rate_limit)
async def create_or_update_user(
    request: Request,
    req: UserRequest,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """Update the *caller's own* identity/musical-preference fields.

    Security (Phase 6 G1): identity is taken from the auth token, never the
    client-supplied ``req.id`` (which is ignored — a body id that differs is
    rejected). Uses ``update_one``/``$set`` on only the mutable fields so a
    call can never clobber ``password_hash`` (which the old whole-document
    ``replace_one`` silently wiped — an unauthenticated account-lockout).
    """
    user_id = principal.user_id
    if req.id and req.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot modify another user")
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "username": req.username,
                "instrument": req.instrument,
                "difficulty": req.difficulty,
                "updated_at": datetime.now(UTC),
            },
            "$setOnInsert": {"_id": user_id, "created_at": datetime.now(UTC)},
        },
        upsert=True,
    )
    return {
        "id": user_id,
        "username": req.username,
        "instrument": req.instrument,
        "difficulty": req.difficulty,
    }


@router.get("/user/{user_id}/preferences")
@limiter.limit(lambda: get_settings().user_rate_limit)
async def get_user_preferences(
    request: Request,
    user_id: str,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
) -> UserPreferences:
    """Read the user's persisted analyze/playback defaults (Plan 3 A8).

    Security (Phase 6 G3): a caller may only read their own preferences. The
    id mismatch is rejected (403) *before* the DB lookup so it can't be used
    to probe which user_ids exist.
    """
    if user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's preferences")
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User profile not registered")
    return UserPreferences(
        default_instrument=user.get("default_instrument") or user.get("instrument"),
        default_difficulty=user.get("default_difficulty") or user.get("difficulty"),
        default_capo=user.get("default_capo"),
    )


@router.put("/user/{user_id}/preferences", response_model=UserPreferences)
@limiter.limit(lambda: get_settings().user_rate_limit)
async def update_user_preferences(
    request: Request,
    user_id: str,
    prefs: UserPreferences,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
) -> UserPreferences:
    """Persist analyze/playback defaults (Plan 3 A8). Upserts the user row.

    Security (Phase 6 G3): a caller may only modify their own preferences
    (403 on id mismatch, checked before any write).
    """
    if user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Cannot modify another user's preferences")
    update: dict[str, object] = {"updated_at": datetime.now(UTC)}
    if prefs.default_instrument is not None:
        update["default_instrument"] = prefs.default_instrument
    if prefs.default_difficulty is not None:
        update["default_difficulty"] = prefs.default_difficulty
    if prefs.default_capo is not None:
        update["default_capo"] = prefs.default_capo
    # Upsert the user row so a preferences-only client (no prior /user POST)
    # still gets a record.
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": update,
            "$setOnInsert": {
                "_id": user_id,
                "username": f"User-{user_id[:6]}",
                "instrument": "guitar",
                "difficulty": "beginner",
                "created_at": datetime.now(UTC),
            },
        },
        upsert=True,
    )
    return prefs


@router.get("/user/{user_id}")
@limiter.limit(lambda: get_settings().user_rate_limit)
async def get_user_profile(
    request: Request,
    user_id: str,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """Fetches registered profile metadata from MongoDB.

    Security (Phase 6 G3): a caller may only read their own profile (403 on
    id mismatch before the lookup).
    """
    if user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's profile")
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User profile not registered")
    # Use .get() with defaults — a user doc created via the chat-profile/upsert
    # path may not carry every field, and hard subscripts would 500.
    created_at = user.get("created_at")
    return {
        "id": user["_id"],
        "username": user.get("username", ""),
        "instrument": user.get("instrument", "guitar"),
        "difficulty": user.get("difficulty", "beginner"),
        "created_at": created_at.isoformat() if isinstance(created_at, datetime) else created_at,
    }
