"""Collections & setlists endpoints — auth, ownership (404), validation, hydration.

Uses the ``as_user`` fixture (require_user → fixed principal) and ``mock_mongo``
(conftest). The ownership rule: missing/unowned → 404, unauth → 401.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from backend.auth import UserPrincipal


@pytest.fixture(autouse=True)
def _auth_env():
    prior = os.environ.get("AUTH_SECRET_KEY")
    os.environ["AUTH_SECRET_KEY"] = "test-secret-please-do-not-use-in-prod"
    from backend.config import get_settings

    get_settings.cache_clear()
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("AUTH_SECRET_KEY", None)
        else:
            os.environ["AUTH_SECRET_KEY"] = prior
        get_settings.cache_clear()


@pytest.fixture
def as_user(mock_mongo):
    """api_client variant with require_user forced to a fixed principal."""
    import backend.database as _dbmod

    _dbmod._db = object()
    from fastapi.testclient import TestClient

    from backend.auth import current_user, require_user
    from backend.database import get_mongodb
    from backend.main import app

    principal = UserPrincipal(user_id="user-1", username="alice")
    app.dependency_overrides[get_mongodb] = lambda: mock_mongo
    app.dependency_overrides[require_user] = lambda: principal
    app.dependency_overrides[current_user] = lambda: principal
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_mongodb, None)
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(current_user, None)


def _set_find_results(coll, docs):
    """Make ``coll.find(...)`` yield ``docs`` from its chainable cursor."""

    async def _aiter(self=None):
        for d in docs:
            yield d

    chain = coll.find.return_value
    chain.__aiter__ = lambda self=chain: _aiter()
    return chain


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------


def test_create_unauthenticated_is_401(api_client):
    # No require_user override → require_user rejects the anonymous caller.
    r = api_client.post("/api/v1/collections", json={"name": "Faves"})
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------


def test_create_returns_id(as_user, mock_mongo):
    r = as_user.post(
        "/api/v1/collections",
        json={"name": "Faves", "kind": "setlist", "description": "gig"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"]
    assert "created_at" in body
    # The saved doc carries owner + server-generated id.
    mock_mongo.collections.replace_one.assert_awaited_once()
    saved = mock_mongo.collections.replace_one.call_args.args[1]
    assert saved["user_id"] == "user-1"
    assert saved["kind"] == "setlist"
    assert saved["name"] == "Faves"


def test_create_empty_name_is_400(as_user):
    r = as_user.post("/api/v1/collections", json={"name": "   "})
    assert r.status_code == 400


def test_create_name_too_long_is_422(as_user):
    # Length violations surface as 422 from Pydantic (distinct from the
    # endpoint's manual empty-name 400).
    r = as_user.post("/api/v1/collections", json={"name": "x" * 121})
    assert r.status_code == 422


# --------------------------------------------------------------------------
# List
# --------------------------------------------------------------------------


def test_list_shape_and_pagination(as_user, mock_mongo):
    docs = [
        {"_id": "c1", "user_id": "user-1", "name": "A", "kind": "collection",
         "description": None, "song_ids": ["j1", "j2"], "created_at": "t1"},
        {"_id": "c2", "user_id": "user-1", "name": "B", "kind": "setlist",
         "description": "d", "song_ids": [], "created_at": "t2"},
    ]
    _set_find_results(mock_mongo.collections, docs)
    mock_mongo.collections.count_documents.return_value = 2

    r = as_user.get("/api/v1/collections?limit=10&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == "c1"
    assert body["items"][0]["song_count"] == 2
    assert body["items"][1]["song_count"] == 0
    # Pagination passthrough to the cursor.
    chain = mock_mongo.collections.find.return_value
    chain.skip.assert_called_once_with(0)
    chain.limit.assert_called_once_with(10)


# --------------------------------------------------------------------------
# Get (+ hydration)
# --------------------------------------------------------------------------


def test_get_unowned_is_404(as_user, mock_mongo):
    mock_mongo.collections.find_one.return_value = None
    r = as_user.get("/api/v1/collections/c-missing")
    assert r.status_code == 404


def test_get_hydrates_songs_in_order_and_filters_unreadable(as_user, mock_mongo):
    mock_mongo.collections.find_one.return_value = {
        "_id": "c1",
        "user_id": "user-1",
        "name": "Faves",
        "kind": "collection",
        "description": None,
        "song_ids": ["j1", "j-missing", "j2", "j-foreign"],
        "created_at": "t1",
        "updated_at": None,
    }
    # song_analyses.find returns the summary docs (unordered, missing j-missing).
    # j-foreign belongs to someone else → must be filtered out.
    song_docs = [
        {"_id": "j2", "title": "Two", "artist": "B", "key": "G", "tempo": 90,
         "duration": 200, "user_id": "user-1"},
        {"_id": "j1", "title": "One", "artist": "A", "key": "C", "tempo": 120,
         "duration": 180, "user_id": None},
        {"_id": "j-foreign", "title": "Secret", "artist": "X", "key": "D",
         "tempo": 100, "duration": 150, "user_id": "user-999"},
    ]
    _set_find_results(mock_mongo.song_analyses, song_docs)

    r = as_user.get("/api/v1/collections/c1")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "c1"
    assert body["song_ids"] == ["j1", "j-missing", "j2", "j-foreign"]
    songs = body["songs"]
    # Order follows song_ids; j-missing skipped (no doc); j-foreign filtered.
    assert [s["job_id"] for s in songs] == ["j1", "j2"]
    assert songs[0]["title"] == "One"
    assert songs[1]["title"] == "Two"


# --------------------------------------------------------------------------
# Update
# --------------------------------------------------------------------------


def test_put_unowned_is_404(as_user, mock_mongo):
    mock_mongo.collections.update_one.return_value = MagicMock(matched_count=0)
    r = as_user.put("/api/v1/collections/c1", json={"name": "New"})
    assert r.status_code == 404


def test_put_empty_name_is_400(as_user):
    r = as_user.put("/api/v1/collections/c1", json={"name": "   "})
    assert r.status_code == 400


def test_put_owned_returns_updated(as_user, mock_mongo):
    mock_mongo.collections.update_one.return_value = MagicMock(matched_count=1)
    r = as_user.put("/api/v1/collections/c1", json={"name": "New", "song_ids": ["j1"]})
    assert r.status_code == 200
    assert r.json() == {"updated": True}
    set_doc = mock_mongo.collections.update_one.call_args.args[1]["$set"]
    assert set_doc["name"] == "New"
    assert set_doc["song_ids"] == ["j1"]


# --------------------------------------------------------------------------
# Delete
# --------------------------------------------------------------------------


def test_delete_unowned_is_404(as_user, mock_mongo):
    mock_mongo.collections.delete_one.return_value = MagicMock(deleted_count=0)
    r = as_user.delete("/api/v1/collections/c1")
    assert r.status_code == 404


def test_delete_owned_returns_deleted(as_user, mock_mongo):
    mock_mongo.collections.delete_one.return_value = MagicMock(deleted_count=1)
    r = as_user.delete("/api/v1/collections/c1")
    assert r.status_code == 200
    assert r.json() == {"deleted": True}


# --------------------------------------------------------------------------
# Add / remove song
# --------------------------------------------------------------------------


def test_add_song_unowned_is_404(as_user, mock_mongo):
    mock_mongo.collections.update_one.return_value = MagicMock(matched_count=0)
    r = as_user.post("/api/v1/collections/c1/songs", json={"job_id": "j9"})
    assert r.status_code == 404


def test_add_song_owned(as_user, mock_mongo):
    mock_mongo.collections.update_one.return_value = MagicMock(matched_count=1)
    r = as_user.post("/api/v1/collections/c1/songs", json={"job_id": "j9"})
    assert r.status_code == 200
    assert r.json() == {"added": True}
    update = mock_mongo.collections.update_one.call_args.args[1]
    assert update["$addToSet"] == {"song_ids": "j9"}


def test_remove_song_unowned_is_404(as_user, mock_mongo):
    mock_mongo.collections.update_one.return_value = MagicMock(matched_count=0)
    r = as_user.delete("/api/v1/collections/c1/songs/j9")
    assert r.status_code == 404


def test_remove_song_owned(as_user, mock_mongo):
    mock_mongo.collections.update_one.return_value = MagicMock(matched_count=1)
    r = as_user.delete("/api/v1/collections/c1/songs/j9")
    assert r.status_code == 200
    assert r.json() == {"removed": True}
