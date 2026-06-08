"""POST /chat — auth, ownership, server-side history, budget (Group D.5).

We override require_user with a fake principal and monkeypatch run_aura so no
model is ever called. mock_mongo (conftest) backs the repos.
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
    """api_client variant with require_user forced to a fixed principal."""
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


def test_unauthenticated_is_401(api_client):
    # api_client does NOT override require_user; with REQUIRE_AUTH unset the
    # dependency still 401s on /chat because the endpoint uses require_user.
    r = api_client.post("/api/v1/chat", json={"message": "hi"})
    assert r.status_code == 401


def test_session_ownership_mismatch_is_403(as_user, mock_mongo, monkeypatch):
    # A session that exists but belongs to someone else → get_owned_session None.
    mock_mongo.chat_sessions.find_one = AsyncMock(return_value=None)

    async def _fake_run_aura(**kwargs):  # pragma: no cover - must not be called
        raise AssertionError("model must not be called on ownership failure")

    monkeypatch.setattr("backend.main.run_aura", _fake_run_aura)
    # Make the session "exist" so we can prove it's the ownership check (not
    # a generate-new-id path) that rejects it.
    monkeypatch.setattr(
        "backend.main._session_exists", AsyncMock(return_value=True)
    )
    r = as_user.post(
        "/api/v1/chat", json={"message": "hi", "session_id": "sess-other"}
    )
    assert r.status_code == 403


def test_history_is_server_side_client_history_ignored(as_user, mock_mongo, monkeypatch):
    # Server returns a known history; the (now-absent) client history can't
    # influence it. We capture what the endpoint passes to run_aura.
    mock_mongo.chat_sessions.find_one = AsyncMock(
        return_value={"_id": "sess-1", "user_id": "user-1",
                      "messages": [{"role": "user", "content": "earlier turn"}]}
    )
    captured: dict = {}

    async def _fake_run_aura(*, message, history, analysis, profile, tutor_mode):
        captured["history"] = history
        captured["message"] = message
        return "ok-reply"

    monkeypatch.setattr("backend.main.run_aura", _fake_run_aura)
    monkeypatch.setattr(
        "backend.main._session_exists", AsyncMock(return_value=True)
    )
    r = as_user.post(
        "/api/v1/chat",
        json={"message": "now", "session_id": "sess-1"},
    )
    assert r.status_code == 200
    assert captured["history"] == [{"role": "user", "content": "earlier turn"}]


def test_over_budget_refuses_without_model_call(as_user, monkeypatch):
    async def _no(*a, **k):
        return False

    monkeypatch.setattr("backend.main.check_and_consume", _no)

    async def _fake_run_aura(**kwargs):  # pragma: no cover
        raise AssertionError("over-budget must not call the model")

    monkeypatch.setattr("backend.main.run_aura", _fake_run_aura)
    r = as_user.post("/api/v1/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert "limit" in r.json()["reply"].lower() or "budget" in r.json()["reply"].lower()


def test_happy_path_persists_two_turns(as_user, mock_mongo, monkeypatch):
    appended: list[tuple] = []

    async def _append(self, session_id, role, content, user_id=None):
        appended.append((role, content))

    monkeypatch.setattr(
        "backend.repositories.ChatSessionRepo.append_turn", _append
    )

    async def _fake_run_aura(**kwargs):
        return "AURA reply"

    monkeypatch.setattr("backend.main.run_aura", _fake_run_aura)
    r = as_user.post("/api/v1/chat", json={"message": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "AURA reply"
    assert body["session_id"]  # server generated one
    roles = [role for role, _ in appended]
    assert roles == ["user", "assistant"]
