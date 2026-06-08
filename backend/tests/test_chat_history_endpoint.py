"""GET /chat/history/{session_id} — owner-only (Group D.7).

The legacy handler had NO auth (anyone could read any session). It now
requires a JWT and only returns history for sessions the caller owns.

I3: the handler must use repo.recent_turns() for the windowed read rather
than pulling the full messages array and Python-slicing it.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

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
    import backend.database as _dbmod

    _dbmod._db = object()
    from fastapi.testclient import TestClient

    from backend.auth import require_user
    from backend.database import get_mongodb
    from backend.main import app

    app.dependency_overrides[get_mongodb] = lambda: mock_mongo
    app.dependency_overrides[require_user] = lambda: UserPrincipal(
        user_id="user-1", username="alice"
    )
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_mongodb, None)
        app.dependency_overrides.pop(require_user, None)


def test_history_requires_auth(api_client):
    r = api_client.get("/api/v1/chat/history/sess-1")
    assert r.status_code == 401


def test_history_returns_owned_session(as_user, mock_mongo, monkeypatch):
    """I3: recent_turns (windowed $slice) is the call that returns history."""
    # get_owned_session: ownership check passes.
    mock_mongo.chat_sessions.find_one = AsyncMock(
        return_value={
            "_id": "sess-1",
            "user_id": "user-1",
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    # recent_turns: windowed read returns the expected slice.
    recent_turns_mock = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
    monkeypatch.setattr(
        "backend.repositories.ChatSessionRepo.recent_turns", recent_turns_mock
    )

    from backend.config import get_settings
    settings = get_settings()

    r = as_user.get("/api/v1/chat/history/sess-1")
    assert r.status_code == 200
    assert r.json()["history"] == [{"role": "user", "content": "hi"}]

    # Lock-in: recent_turns was called with the right session_id and window.
    recent_turns_mock.assert_awaited_once_with("sess-1", settings.chat_history_turns)


def test_history_rejects_foreign_session(as_user, mock_mongo):
    # get_owned_session filters by user_id, so a foreign session → None → 404.
    mock_mongo.chat_sessions.find_one = AsyncMock(return_value=None)
    r = as_user.get("/api/v1/chat/history/sess-foreign")
    assert r.status_code == 404
