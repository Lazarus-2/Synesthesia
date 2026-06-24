"""Tests for CollectionRepo (collections + ordered setlists).

Hermetic — driven by the ``mock_mongo`` fixture (conftest). Ownership is
enforced in the query filter ({_id, user_id}) so a caller can't touch another
user's collection.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestGetOwned:
    @pytest.mark.asyncio
    async def test_returns_doc_when_owner_matches(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.find_one.return_value = {
            "_id": "c1",
            "user_id": "u1",
            "name": "Faves",
        }
        repo = CollectionRepo(mock_mongo)
        doc = await repo.get_owned("c1", "u1")

        assert doc is not None
        assert doc["_id"] == "c1"
        mock_mongo.collections.find_one.assert_awaited_once_with(
            {"_id": "c1", "user_id": "u1"}
        )

    @pytest.mark.asyncio
    async def test_returns_none_on_mismatch(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.find_one.return_value = None
        repo = CollectionRepo(mock_mongo)
        doc = await repo.get_owned("c1", "intruder")

        assert doc is None
        mock_mongo.collections.find_one.assert_awaited_once_with(
            {"_id": "c1", "user_id": "intruder"}
        )


class TestListOwned:
    @pytest.mark.asyncio
    async def test_returns_docs_and_total_with_pagination(self, mock_mongo):
        from backend.repositories import CollectionRepo

        docs = [
            {"_id": "c1", "user_id": "u1", "name": "A"},
            {"_id": "c2", "user_id": "u1", "name": "B"},
        ]

        async def _aiter(self=None):
            for d in docs:
                yield d

        chain = mock_mongo.collections.find.return_value
        chain.__aiter__ = lambda self=chain: _aiter()
        mock_mongo.collections.count_documents.return_value = 7

        repo = CollectionRepo(mock_mongo)
        result, total = await repo.list_owned("u1", skip=5, limit=2)

        assert result == docs
        assert total == 7
        mock_mongo.collections.count_documents.assert_awaited_once_with({"user_id": "u1"})
        mock_mongo.collections.find.assert_called_once_with({"user_id": "u1"})
        chain.sort.assert_called_once_with("created_at", -1)
        chain.skip.assert_called_once_with(5)
        chain.limit.assert_called_once_with(2)


class TestSave:
    @pytest.mark.asyncio
    async def test_upserts_by_id(self, mock_mongo):
        from backend.repositories import CollectionRepo

        repo = CollectionRepo(mock_mongo)
        doc = {"_id": "c1", "user_id": "u1", "name": "A"}
        await repo.save("c1", doc)

        mock_mongo.collections.replace_one.assert_awaited_once_with(
            {"_id": "c1"}, doc, upsert=True
        )


class TestDelete:
    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.delete_one.return_value = MagicMock(deleted_count=1)
        repo = CollectionRepo(mock_mongo)
        assert await repo.delete("c1", "u1") is True
        mock_mongo.collections.delete_one.assert_awaited_once_with(
            {"_id": "c1", "user_id": "u1"}
        )

    @pytest.mark.asyncio
    async def test_returns_false_when_nothing_deleted(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.delete_one.return_value = MagicMock(deleted_count=0)
        repo = CollectionRepo(mock_mongo)
        assert await repo.delete("c1", "intruder") is False


class TestUpdate:
    @pytest.mark.asyncio
    async def test_returns_true_and_sets_fields_plus_updated_at(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.update_one.return_value = MagicMock(matched_count=1)
        repo = CollectionRepo(mock_mongo)
        ok = await repo.update("c1", "u1", {"name": "New"})

        assert ok is True
        call = mock_mongo.collections.update_one.call_args
        assert call.args[0] == {"_id": "c1", "user_id": "u1"}
        set_doc = call.args[1]["$set"]
        assert set_doc["name"] == "New"
        assert "updated_at" in set_doc

    @pytest.mark.asyncio
    async def test_returns_false_when_unmatched(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.update_one.return_value = MagicMock(matched_count=0)
        repo = CollectionRepo(mock_mongo)
        assert await repo.update("c1", "intruder", {"name": "New"}) is False


class TestAddSong:
    @pytest.mark.asyncio
    async def test_returns_true_and_addtoset(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.update_one.return_value = MagicMock(matched_count=1)
        repo = CollectionRepo(mock_mongo)
        ok = await repo.add_song("c1", "u1", "job-9")

        assert ok is True
        call = mock_mongo.collections.update_one.call_args
        assert call.args[0] == {"_id": "c1", "user_id": "u1"}
        update = call.args[1]
        assert update["$addToSet"] == {"song_ids": "job-9"}
        assert "updated_at" in update["$set"]

    @pytest.mark.asyncio
    async def test_returns_false_when_unmatched(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.update_one.return_value = MagicMock(matched_count=0)
        repo = CollectionRepo(mock_mongo)
        assert await repo.add_song("c1", "intruder", "job-9") is False


class TestRemoveSong:
    @pytest.mark.asyncio
    async def test_returns_true_and_pull(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.update_one.return_value = MagicMock(matched_count=1)
        repo = CollectionRepo(mock_mongo)
        ok = await repo.remove_song("c1", "u1", "job-9")

        assert ok is True
        call = mock_mongo.collections.update_one.call_args
        assert call.args[0] == {"_id": "c1", "user_id": "u1"}
        update = call.args[1]
        assert update["$pull"] == {"song_ids": "job-9"}
        assert "updated_at" in update["$set"]

    @pytest.mark.asyncio
    async def test_returns_false_when_unmatched(self, mock_mongo):
        from backend.repositories import CollectionRepo

        mock_mongo.collections.update_one.return_value = MagicMock(matched_count=0)
        repo = CollectionRepo(mock_mongo)
        assert await repo.remove_song("c1", "intruder", "job-9") is False
