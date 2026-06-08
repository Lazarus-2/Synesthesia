"""Repository for the ``users`` collection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class UserRepo:
    """Owns reads/writes to ``users``."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._coll = db.users

    async def get(self, user_id: str) -> dict[str, Any] | None:
        """Return the user doc by id, or None."""
        return await self._coll.find_one({"_id": user_id})

    async def upsert(self, user_id: str, fields: dict[str, Any]) -> None:
        """Insert-or-update a user. ``fields`` go into ``$set`` (mutable);
        ``_id`` and ``created_at`` are seeded via ``$setOnInsert`` so a
        re-upsert never clobbers the original creation time.

        ``_id`` and ``created_at`` are stripped from ``fields`` before
        building ``$set`` so a caller that accidentally passes them cannot
        overwrite those immutable fields on an existing document.
        """
        safe_fields = {k: v for k, v in fields.items() if k not in ("_id", "created_at")}
        await self._coll.update_one(
            {"_id": user_id},
            {
                "$set": safe_fields,
                "$setOnInsert": {"_id": user_id, "created_at": datetime.now(UTC)},
            },
            upsert=True,
        )
