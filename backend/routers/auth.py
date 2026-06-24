"""Auth (Plan 3 A9) — sign-up / login over the JWT skeleton from Plan 2 D4."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.config import get_settings
from backend.database import get_mongodb
from backend.ratelimit import limiter

router = APIRouter()


class SignUpRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    username: str


@router.post("/auth/signup", response_model=AuthResponse)
@limiter.limit(lambda: get_settings().auth_rate_limit)
async def signup(request: Request, req: SignUpRequest, db=Depends(get_mongodb)) -> AuthResponse:
    """Create a user with a hashed password and return a JWT (Plan 3 A9).

    Idempotency: returns 409 if the username is already taken. Note that
    the server still operates in anonymous-friendly mode unless
    ``REQUIRE_AUTH=true`` — sign-up is opt-in for users who want
    persistent libraries / preferences.
    """
    from pymongo.errors import DuplicateKeyError

    from backend.auth import hash_password, issue_token

    if not req.username.strip() or len(req.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Username required and password must be at least 8 characters",
        )
    if await db.users.find_one({"username": req.username}):
        raise HTTPException(status_code=409, detail="Username already taken")
    user_id = str(uuid.uuid4())
    try:
        await db.users.insert_one(
            {
                "_id": user_id,
                "username": req.username,
                "instrument": "guitar",
                "difficulty": "beginner",
                "password_hash": hash_password(req.password),
                "created_at": datetime.now(UTC),
            }
        )
    except DuplicateKeyError:
        # Lost a concurrent signup race — the unique username index is the
        # authoritative guard (the find_one check above is not atomic).
        raise HTTPException(status_code=409, detail="Username already taken")
    try:
        token = issue_token(user_id=user_id, username=req.username)
    except RuntimeError as e:
        # auth_secret_key not configured — still create the user, but the
        # client gets a clear 503 instead of a cryptic 500.
        raise HTTPException(status_code=503, detail=str(e))
    return AuthResponse(token=token, user_id=user_id, username=req.username)


@router.post("/auth/login", response_model=AuthResponse)
@limiter.limit(lambda: get_settings().auth_rate_limit)
async def login(request: Request, req: LoginRequest, db=Depends(get_mongodb)) -> AuthResponse:
    """Verify password and return a JWT (Plan 3 A9)."""
    from backend.auth import issue_token, verify_password

    user = await db.users.find_one({"username": req.username})
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    try:
        token = issue_token(user_id=user["_id"], username=user["username"])
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return AuthResponse(token=token, user_id=user["_id"], username=user["username"])


@router.get("/auth/me")
async def whoami(request: Request) -> dict:
    """Return the authenticated principal, or ``null`` when anonymous."""
    from backend.auth import current_user

    principal = current_user(request)
    if principal is None:
        return {"user": None}
    return {"user": {"user_id": principal.user_id, "username": principal.username}}
