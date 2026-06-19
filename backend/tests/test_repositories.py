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


class TestUserRepo:
    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self, mock_mongo):
        from backend.repositories import UserRepo

        mock_mongo.users.find_one.return_value = None
        repo = UserRepo(mock_mongo)
        assert await repo.get("usr_missing") is None
        mock_mongo.users.find_one.assert_awaited_once_with({"_id": "usr_missing"})

    @pytest.mark.asyncio
    async def test_get_returns_doc(self, mock_mongo):
        from backend.repositories import UserRepo

        mock_mongo.users.find_one.return_value = {"_id": "usr_1", "username": "Ada"}
        repo = UserRepo(mock_mongo)
        doc = await repo.get("usr_1")
        assert doc["username"] == "Ada"

    @pytest.mark.asyncio
    async def test_upsert_sets_on_insert_only_for_immutable_fields(self, mock_mongo):
        from backend.repositories import UserRepo

        repo = UserRepo(mock_mongo)
        await repo.upsert("usr_1", {"username": "Ada", "instrument": "piano"})

        mock_mongo.users.update_one.assert_awaited_once()
        call = mock_mongo.users.update_one.call_args
        assert call.args[0] == {"_id": "usr_1"}
        # $set carries the mutable fields; $setOnInsert seeds _id + created_at.
        update = call.args[1]
        assert update["$set"] == {"username": "Ada", "instrument": "piano"}
        assert update["$setOnInsert"]["_id"] == "usr_1"
        assert "created_at" in update["$setOnInsert"]
        assert call.kwargs == {"upsert": True}


class TestChatSessionRepo:
    @pytest.mark.asyncio
    async def test_get_owned_session_returns_none_on_mismatch(self, mock_mongo):
        from backend.repositories import ChatSessionRepo

        mock_mongo.chat_sessions.find_one.return_value = None
        repo = ChatSessionRepo(mock_mongo)
        doc = await repo.get_owned_session("sess_1", "intruder")

        assert doc is None
        mock_mongo.chat_sessions.find_one.assert_awaited_once_with(
            {"_id": "sess_1", "user_id": "intruder"}
        )

    @pytest.mark.asyncio
    async def test_get_owned_session_returns_doc(self, mock_mongo):
        from backend.repositories import ChatSessionRepo

        mock_mongo.chat_sessions.find_one.return_value = {
            "_id": "sess_1",
            "user_id": "usr_1",
            "messages": [],
        }
        repo = ChatSessionRepo(mock_mongo)
        doc = await repo.get_owned_session("sess_1", "usr_1")
        assert doc["_id"] == "sess_1"

    @pytest.mark.asyncio
    async def test_append_turn_pushes_message(self, mock_mongo):
        from backend.repositories import ChatSessionRepo

        repo = ChatSessionRepo(mock_mongo)
        await repo.append_turn("sess_1", "user", "How do I play C?")

        mock_mongo.chat_sessions.update_one.assert_awaited_once()
        call = mock_mongo.chat_sessions.update_one.call_args
        assert call.args[0] == {"_id": "sess_1"}
        pushed = call.args[1]["$push"]["messages"]
        assert pushed["role"] == "user"
        assert pushed["content"] == "How do I play C?"
        assert "timestamp" in pushed
        # Must upsert so calling append_turn on a non-existent session creates it.
        assert call.kwargs.get("upsert") is True

    @pytest.mark.asyncio
    async def test_append_turn_upsert_with_user_id(self, mock_mongo):
        """user_id must land in $setOnInsert when provided (ownership seeding)."""
        from backend.repositories import ChatSessionRepo

        repo = ChatSessionRepo(mock_mongo)
        await repo.append_turn("sess_new", "user", "Hello", user_id="usr_42")

        call = mock_mongo.chat_sessions.update_one.call_args
        assert call.kwargs.get("upsert") is True
        set_on_insert = call.args[1]["$setOnInsert"]
        assert set_on_insert["user_id"] == "usr_42"
        assert "created_at" in set_on_insert
        # messages must NOT appear in $setOnInsert — $push handles array creation.
        assert "messages" not in set_on_insert

    @pytest.mark.asyncio
    async def test_append_turn_upsert_without_user_id(self, mock_mongo):
        """user_id must be absent from $setOnInsert when not provided (anonymous session)."""
        from backend.repositories import ChatSessionRepo

        repo = ChatSessionRepo(mock_mongo)
        await repo.append_turn("sess_anon", "assistant", "Hi there")

        call = mock_mongo.chat_sessions.update_one.call_args
        assert call.kwargs.get("upsert") is True
        set_on_insert = call.args[1]["$setOnInsert"]
        assert "user_id" not in set_on_insert
        assert "created_at" in set_on_insert

    @pytest.mark.asyncio
    async def test_recent_turns_windows_via_slice_projection(self, mock_mongo):
        from backend.repositories import ChatSessionRepo

        # Mongo applies the $slice; the mock just returns the already-windowed
        # tail. We assert BOTH the projection (server-side window) and output.
        mock_mongo.chat_sessions.find_one.return_value = {
            "_id": "sess_1",
            "messages": [
                {"role": "user", "content": "m4"},
                {"role": "assistant", "content": "m5"},
            ],
        }
        repo = ChatSessionRepo(mock_mongo)
        turns = await repo.recent_turns("sess_1", 2)

        # Windowing happens in the query, not a Python slice of a full doc.
        mock_mongo.chat_sessions.find_one.assert_awaited_once_with(
            {"_id": "sess_1"}, {"messages": {"$slice": -2}}
        )
        assert turns == [
            {"role": "user", "content": "m4"},
            {"role": "assistant", "content": "m5"},
        ]

    @pytest.mark.asyncio
    async def test_recent_turns_empty_for_missing_session(self, mock_mongo):
        from backend.repositories import ChatSessionRepo

        mock_mongo.chat_sessions.find_one.return_value = None
        repo = ChatSessionRepo(mock_mongo)
        assert await repo.recent_turns("sess_nope", 5) == []

    @pytest.mark.asyncio
    async def test_recent_turns_raises_for_zero_n(self, mock_mongo):
        """n=0 is silently wrong ($slice: 0 returns nothing); must raise."""
        from backend.repositories import ChatSessionRepo

        repo = ChatSessionRepo(mock_mongo)
        with pytest.raises(ValueError, match="n must be positive"):
            await repo.recent_turns("sess_1", 0)

    @pytest.mark.asyncio
    async def test_recent_turns_raises_for_negative_n(self, mock_mongo):
        """n<0 would make $slice: -(-n) = $slice: positive which returns the
        FIRST messages — silently wrong; must raise."""
        from backend.repositories import ChatSessionRepo

        repo = ChatSessionRepo(mock_mongo)
        with pytest.raises(ValueError, match="n must be positive"):
            await repo.recent_turns("sess_1", -3)

    @pytest.mark.asyncio
    async def test_recent_turns_empty_when_doc_has_no_messages_key(self, mock_mongo):
        """Session exists but has no 'messages' field yet → returns [] via doc.get('messages', [])."""
        from backend.repositories import ChatSessionRepo

        mock_mongo.chat_sessions.find_one.return_value = {
            "_id": "sess_empty",
            "user_id": "usr_1",
            # no 'messages' key at all
        }
        repo = ChatSessionRepo(mock_mongo)
        result = await repo.recent_turns("sess_empty", 10)
        assert result == []


class TestChatHistoryRefactor:
    def test_history_route_requires_auth_and_returns_owned_session(
        self, mock_mongo
    ):
        """GET /chat/history now requires JWT (D.7). An authenticated owner gets
        their messages; the legacy unauthenticated path is gone."""
        import os
        from unittest.mock import AsyncMock

        from fastapi.testclient import TestClient

        import backend.database as _dbmod
        from backend.auth import UserPrincipal, require_user
        from backend.database import get_mongodb
        from backend.main import app

        os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-please-do-not-use-in-prod")

        _dbmod._db = object()
        mock_mongo.chat_sessions.find_one = AsyncMock(
            return_value={
                "_id": "test_slice_sess",
                "user_id": "user-1",
                "messages": [{"role": "user", "content": "hi"}],
            }
        )
        app.dependency_overrides[get_mongodb] = lambda: mock_mongo
        app.dependency_overrides[require_user] = lambda: UserPrincipal(
            user_id="user-1", username="alice"
        )
        try:
            client = TestClient(app, raise_server_exceptions=False)
            r = client.get("/api/v1/chat/history/test_slice_sess")
            assert r.status_code == 200
            assert r.json()["history"] == [{"role": "user", "content": "hi"}]
        finally:
            app.dependency_overrides.pop(get_mongodb, None)
            app.dependency_overrides.pop(require_user, None)


class TestShareRefactor:
    def test_share_404_when_missing(self, api_client, mock_mongo):
        mock_mongo.song_analyses.find_one.return_value = None
        r = api_client.get("/api/v1/share/job_missing")
        assert r.status_code == 404

    def test_share_reads_by_id_via_repo(self, api_client, mock_mongo):
        mock_mongo.song_analyses.find_one.return_value = {
            "_id": "job_1",
            "duration": 10.0,
            "key": "C major",
            "tempo": 120.0,
            "chords": [],
        }
        r = api_client.get("/api/v1/share/job_1")
        assert r.status_code == 200
        assert r.json()["job_id"] == "job_1"
        mock_mongo.song_analyses.find_one.assert_awaited_once_with({"_id": "job_1"})
