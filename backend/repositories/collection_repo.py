"""Repository for the ``collections`` collection (collections + setlists).

Documents are discriminated by ``kind`` ("collection" | "setlist"); both carry
an ordered ``song_ids`` list. Every read/write filters by ``user_id`` so a
caller can't touch another user's collection (ID-01 ownership rule).
"""

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class CollectionRepo:
    """Owns reads/writes to ``collections`` (collections + ordered setlists)."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._coll = db.collections

    async def get_owned(self, cid: str, user_id: str) -> dict[str, Any] | None:
        return await self._coll.find_one({"_id": cid, "user_id": user_id})

    async def list_owned(
        self, user_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[dict[str, Any]], int]:
        total = await self._coll.count_documents({"user_id": user_id})
        cursor = self._coll.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit)
        docs: list[dict[str, Any]] = []
        async for doc in cursor:
            docs.append(doc)
        return docs, total

    async def save(self, cid: str, doc: dict[str, Any]) -> None:
        await self._coll.replace_one({"_id": cid}, doc, upsert=True)

    async def delete(self, cid: str, user_id: str) -> bool:
        res = await self._coll.delete_one({"_id": cid, "user_id": user_id})
        return res.deleted_count > 0

    async def update(self, cid: str, user_id: str, fields: dict[str, Any]) -> bool:
        res = await self._coll.update_one(
            {"_id": cid, "user_id": user_id},
            {"$set": {**fields, "updated_at": datetime.now(UTC)}},
        )
        return res.matched_count > 0

    async def add_song(self, cid: str, user_id: str, job_id: str) -> bool:
        res = await self._coll.update_one(
            {"_id": cid, "user_id": user_id},
            {"$addToSet": {"song_ids": job_id}, "$set": {"updated_at": datetime.now(UTC)}},
        )
        return res.matched_count > 0

    async def remove_song(self, cid: str, user_id: str, job_id: str) -> bool:
        res = await self._coll.update_one(
            {"_id": cid, "user_id": user_id},
            {"$pull": {"song_ids": job_id}, "$set": {"updated_at": datetime.now(UTC)}},
        )
        return res.matched_count > 0
