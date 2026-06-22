"""JWT auth skeleton (Plan 2 D4) — opt-in.

Default deployment is anonymous-access: ``require_auth=False`` makes every
endpoint accept callers without a token, and :func:`current_user` resolves
to ``None``. Flip ``REQUIRE_AUTH=true`` per deploy to enforce JWT on every
route that ``Depends(current_user)``.

What's here vs deferred
-----------------------
Included:
  - JWT issue + verify
  - bcrypt password hash + verify
  - ``current_user`` FastAPI dependency (optional/required modes)
  - Pydantic ``UserPrincipal`` returned to endpoints

Deferred to its own session:
  - Sign-up / login REST endpoints (frontend pairing — Plan 3 A9)
  - Refresh-token rotation
  - Role-based access control (single ``user_id`` claim is enough for MVP)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from backend.config import get_settings

_BEARER_PREFIX = "Bearer "


class UserPrincipal(BaseModel):
    """The authenticated caller. Returned by :func:`current_user`."""

    user_id: str
    username: str | None = None


# ---- Passwords -------------------------------------------------------------
def hash_password(plain: str) -> str:
    """Hash a password using bcrypt. Returns the encoded hash string."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time compare of a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---- JWT -------------------------------------------------------------------
def issue_token(
    *, user_id: str, username: str | None = None, expires_minutes: int | None = None
) -> str:
    """Sign and return a JWT for the given user."""
    s = get_settings()
    if not s.auth_secret_key:
        raise RuntimeError(
            "Cannot issue token: AUTH_SECRET_KEY is empty. "
            "Set REQUIRE_AUTH+AUTH_SECRET_KEY in your env."
        )
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=expires_minutes or s.auth_jwt_expire_minutes)
    payload: dict[str, object] = {
        "sub": user_id,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, s.auth_secret_key, algorithm=s.auth_jwt_algorithm)


def decode_token(token: str) -> UserPrincipal:
    """Verify signature + expiry; return a :class:`UserPrincipal`.

    Raises :class:`HTTPException` 401 on any failure so the FastAPI exception
    handler can format the standard error envelope.
    """
    s = get_settings()
    if not s.auth_secret_key:
        raise HTTPException(status_code=401, detail="Authentication is not configured")
    try:
        # algorithms is a single-element allowlist (HS256 by default) so PyJWT
        # rejects any other alg — including "none" — closing alg-confusion.
        # require=[exp,sub] rejects tokens lacking an expiry (never-expiring) or
        # subject, rather than silently accepting them.
        payload = jwt.decode(
            token,
            s.auth_secret_key,
            algorithms=[s.auth_jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Token missing user subject")
    return UserPrincipal(user_id=sub, username=payload.get("username"))


# ---- FastAPI dependency ----------------------------------------------------
def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header or not header.startswith(_BEARER_PREFIX):
        return None
    token = header[len(_BEARER_PREFIX) :].strip()
    return token or None


def current_user(request: Request) -> UserPrincipal | None:
    """Resolve the authenticated user, or return None when auth is disabled.

    Behavior:
      - ``require_auth=False`` (default): always returns None. Endpoints that
        want to optionally surface the user can still check the return value.
      - ``require_auth=True``: a missing/invalid token raises 401. A valid
        token returns a :class:`UserPrincipal`.
    """
    s = get_settings()
    token = _extract_bearer(request)

    if not s.require_auth:
        if not token:
            return None
        try:
            return decode_token(token)
        except HTTPException:
            # If a caller sends a token in anonymous mode and it's bad, the
            # endpoint can still serve the request — we don't want a corrupt
            # cookie to break public flows. Return None instead of raising.
            return None

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return decode_token(token)


def require_user(
    user: Annotated[UserPrincipal | None, Depends(current_user)],
) -> UserPrincipal:
    """Dependency variant that always requires a user, regardless of config.

    Use this on endpoints that must always authenticate (e.g. account
    management) even in deployments that allow anonymous analyze/chat.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
