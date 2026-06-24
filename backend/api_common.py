"""Shared API helpers used across more than one router module.

Only helpers needed on BOTH sides of a router split live here. Imports are
restricted to config/auth/database/repositories/services/schemas — never
``backend.main`` or any router module, to avoid import cycles.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.auth import UserPrincipal


async def _enforce_owned_read(
    job_id: str,
    principal: UserPrincipal | None,
    db: Any,
    *,
    allow_missing: bool = False,
) -> None:
    """404 when an authenticated caller requests another user's OWNED job (Phase 6 G2).

    No-op for anonymous callers (``principal is None``) — in the default
    anonymous deployment every analysis is public, and the public ``/share``
    player fetches media token-less, so those flows are unchanged. Anonymous
    docs (``user_id is None``) stay readable for everyone. ``allow_missing``
    lets the progress SSE keep streaming an in-flight job whose final doc is
    not written yet (ownership isn't determinable then; low-sensitivity).
    """
    if principal is None:
        return
    doc = await db.song_analyses.find_one({"_id": job_id}, {"user_id": 1})
    if doc is None:
        if allow_missing:
            return
        raise HTTPException(status_code=404, detail="Not found")
    owner = doc.get("user_id")
    if owner is not None and owner != principal.user_id:
        raise HTTPException(status_code=404, detail="Not found")


def _reject_job_id_traversal(job_id: str) -> None:
    """Reject a job_id that could escape its storage dir via path separators."""
    if "/" in job_id or "\\" in job_id or ".." in job_id:
        raise HTTPException(status_code=404, detail="Not found")
