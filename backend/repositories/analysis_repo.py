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

    async def resolve_readable(
        self, job_id: str, requester_user_id: str | None
    ) -> dict[str, Any] | None:
        """Return the doc the requester is allowed to read, else ``None`` (Phase 6 G1).

        The single ownership rule for every analysis-keyed media/read endpoint:

        - missing doc -> ``None`` (caller returns 404);
        - anonymous doc (``user_id is None``) -> readable by anyone, incl.
          token-less callers and the public ``/share`` flow;
        - owned doc -> readable only when ``requester_user_id`` matches the
          owner; any mismatch (or anonymous requester) -> ``None``.

        Endpoints map a ``None`` result to 404 (not 403) so an authenticated
        attacker can't use the response to confirm another user's job exists.
        """
        doc = await self.get(job_id)
        if doc is None:
            return None
        owner = doc.get("user_id")
        if owner is None:
            return doc  # anonymous / public — preserves anon + /share
        if requester_user_id is not None and requester_user_id == owner:
            return doc
        return None

    async def save(self, job_id: str, doc: dict[str, Any]) -> None:
        """Upsert ``doc`` keyed by ``job_id`` via a whole-document replace.

        WARNING — this is DESTRUCTIVE: ``replace_one`` replaces the entire
        document, not just the fields you pass.  Callers MUST supply the
        complete document including ``user_id``, ``status``, and ``file_hash``
        or those fields will be lost on re-save.  The canonical source is
        ``SongAnalysisModel.model_dump(by_alias=True)``.
        """
        await self._coll.replace_one({"_id": job_id}, doc, upsert=True)
