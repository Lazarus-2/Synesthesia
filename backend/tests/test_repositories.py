"""Tests for the async repository layer + user_id ownership (Group 5 / ID-01).

Repos are thin async wrappers over Motor collections. Tests drive them with
the ``mock_mongo`` fixture from conftest.py so they stay hermetic — no live
Mongo, no network. The fixture's collections expose ``find_one``,
``insert_one``, ``update_one``, ``replace_one`` as AsyncMocks and ``find`` as
a self-chaining async-iterable.
"""

from __future__ import annotations

import pytest

from backend.models import SongAnalysisModel


class TestSongAnalysisUserId:
    def test_user_id_defaults_to_none(self):
        song = SongAnalysisModel(
            id="job_1", duration=10.0, key="C major", tempo=120.0
        )
        assert song.user_id is None

    def test_user_id_round_trips(self):
        song = SongAnalysisModel(
            id="job_2", duration=10.0, key="C major", tempo=120.0, user_id="usr_9"
        )
        assert song.user_id == "usr_9"
        assert song.model_dump()["user_id"] == "usr_9"


class TestIndexes:
    @pytest.mark.asyncio
    async def test_user_id_index_created(self, mock_mongo):
        from unittest.mock import AsyncMock

        from backend.database import _create_indexes

        mock_mongo.users.create_index = AsyncMock()
        mock_mongo.chat_sessions.create_index = AsyncMock()
        mock_mongo.song_analyses.create_index = AsyncMock()
        mock_mongo.failed_jobs.create_index = AsyncMock()

        await _create_indexes(mock_mongo)

        created = [c.args[0] for c in mock_mongo.song_analyses.create_index.call_args_list]
        assert "user_id" in created


class TestAnalysisRepo:
    @pytest.mark.asyncio
    async def test_get_owned_returns_doc_when_owner_matches(self, mock_mongo):
        from backend.repositories import AnalysisRepo

        mock_mongo.song_analyses.find_one.return_value = {
            "_id": "job_1",
            "user_id": "usr_1",
            "duration": 10.0,
            "key": "C major",
            "tempo": 120.0,
        }
        repo = AnalysisRepo(mock_mongo)
        doc = await repo.get_owned("job_1", "usr_1")

        assert doc is not None
        assert doc["_id"] == "job_1"
        mock_mongo.song_analyses.find_one.assert_awaited_once_with(
            {"_id": "job_1", "user_id": "usr_1"}
        )

    @pytest.mark.asyncio
    async def test_get_owned_returns_none_on_ownership_mismatch(self, mock_mongo):
        from backend.repositories import AnalysisRepo

        # Mongo returns nothing because the {_id, user_id} filter doesn't match.
        mock_mongo.song_analyses.find_one.return_value = None
        repo = AnalysisRepo(mock_mongo)
        doc = await repo.get_owned("job_1", "intruder")

        assert doc is None
        mock_mongo.song_analyses.find_one.assert_awaited_once_with(
            {"_id": "job_1", "user_id": "intruder"}
        )

    @pytest.mark.asyncio
    async def test_save_upserts_by_id(self, mock_mongo):
        from backend.repositories import AnalysisRepo

        repo = AnalysisRepo(mock_mongo)
        await repo.save("job_7", {"_id": "job_7", "key": "G major"})

        mock_mongo.song_analyses.replace_one.assert_awaited_once_with(
            {"_id": "job_7"}, {"_id": "job_7", "key": "G major"}, upsert=True
        )
