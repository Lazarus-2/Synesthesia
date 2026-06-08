"""Repository for the ``song_analyses`` collection."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class AnalysisRepo:
    """Owns reads/writes to ``song_analyses``.

    ``get_owned`` always filters by ``user_id`` so a caller can't read another
    user's analysis by guessing a job_id (ID-01). Pass the caller's own
    ``user_id``; a mismatch (or anonymous doc) returns ``None``.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._coll = db.song_analyses

    async def get_owned(self, job_id: str, user_id: str) -> dict[str, Any] | None:
        """Return the analysis doc iff it exists AND belongs to ``user_id``."""
        return await self._coll.find_one({"_id": job_id, "user_id": user_id})

    async def get(self, job_id: str) -> dict[str, Any] | None:
        """Return the analysis doc by id with no ownership check.

        Only for explicitly public/read-only paths (e.g. /share). Authenticated
        callers must use ``get_owned``.
        """
        return await self._coll.find_one({"_id": job_id})

    async def save(self, job_id: str, doc: dict[str, Any]) -> None:
        """Upsert ``doc`` keyed by ``job_id`` (replace whole document)."""
        await self._coll.replace_one({"_id": job_id}, doc, upsert=True)
