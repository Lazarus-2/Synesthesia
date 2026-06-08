"""Repository for the ``chat_sessions`` collection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class ChatSessionRepo:
    """Owns reads/writes to ``chat_sessions``.

    ``recent_turns`` windows server-side with a ``$slice`` projection so we
    never pull a full (potentially long) ``messages`` array just to keep the
    tail — that was the inline pattern in main.py this repo replaces.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._coll = db.chat_sessions

    async def get_owned_session(
        self, session_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Return the session iff it exists AND belongs to ``user_id``."""
        return await self._coll.find_one({"_id": session_id, "user_id": user_id})

    async def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
    ) -> None:
        """Push one message onto the session's ``messages`` array.

        Upserts the session document so that calling ``append_turn`` on a
        session that doesn't yet exist creates it rather than silently no-oping.
        ``user_id`` is seeded via ``$setOnInsert`` when provided (ownership
        tracking); it is omitted entirely when ``None`` so anonymous sessions
        remain valid.  Note: ``messages`` must NOT appear in ``$setOnInsert``
        — ``$push`` handles array creation on insert automatically.
        """
        set_on_insert: dict = {"created_at": datetime.now(UTC)}
        if user_id is not None:
            set_on_insert["user_id"] = user_id
        await self._coll.update_one(
            {"_id": session_id},
            {
                "$push": {
                    "messages": {
                        "role": role,
                        "content": content,
                        "timestamp": datetime.now(UTC),
                    }
                },
                "$setOnInsert": set_on_insert,
            },
            upsert=True,
        )

    async def recent_turns(self, session_id: str, n: int) -> list[dict[str, Any]]:
        """Return the last ``n`` messages, windowed in Mongo via ``$slice``.

        Raises ``ValueError`` if ``n <= 0``: ``{"$slice": 0}`` returns an empty
        array and ``{"$slice": -n}`` with a negative ``n`` silently returns the
        *first* messages — both are operationally wrong for a "recent turns"
        query.
        """
        if n <= 0:
            raise ValueError(f"recent_turns: n must be positive, got {n}")
        doc = await self._coll.find_one(
            {"_id": session_id}, {"messages": {"$slice": -n}}
        )
        if not doc:
            return []
        return [
            {"role": m["role"], "content": m["content"]}
            for m in doc.get("messages", [])
        ]
