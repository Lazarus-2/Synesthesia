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

    from backend.auth import current_user, require_user
    from backend.database import get_mongodb
    from backend.main import app

    principal = UserPrincipal(user_id="user-1", username="alice")
    app.dependency_overrides[get_mongodb] = lambda: mock_mongo
    app.dependency_overrides[require_user] = lambda: principal
    # /chat + /chat/stream use current_user (anonymous-allowed); override it too
    # so authenticated-path tests get a real principal.
    app.dependency_overrides[current_user] = lambda: principal
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_mongodb, None)
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(current_user, None)


def test_unauthenticated_allowed_in_anonymous_mode(api_client, monkeypatch):
    # /chat uses current_user (not require_user): with REQUIRE_AUTH unset
    # (anonymous mode, the default), an unauthenticated caller is allowed and
    # chats under a shared "anonymous" identity rather than being rejected.
    async def _fake_run_aura(**kwargs):
        return "anon reply"

    monkeypatch.setattr("backend.main.run_aura", _fake_run_aura)
    r = api_client.post("/api/v1/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert r.json()["reply"] == "anon reply"


def test_session_ownership_mismatch_is_403(as_user, mock_mongo, monkeypatch):
    # A session that exists but belongs to someone else → 403.
    # _resolve_session does a single find_one then checks user_id ownership.
    mock_mongo.chat_sessions.find_one = AsyncMock(
        return_value={"_id": "sess-other", "user_id": "user-999"}
    )

    async def _fake_run_aura(**kwargs):  # pragma: no cover - must not be called
        raise AssertionError("model must not be called on ownership failure")

    monkeypatch.setattr("backend.main.run_aura", _fake_run_aura)
    r = as_user.post(
        "/api/v1/chat", json={"message": "hi", "session_id": "sess-other"}
    )
    assert r.status_code == 403


def test_history_is_server_side_recent_turns_used(as_user, mock_mongo, monkeypatch):
    """recent_turns (windowed $slice query) must be the call that supplies
    the agent's history — not a full-doc Python slice.  Lock in the call."""
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

    # Patch recent_turns to assert it's called with the right args and return
    # a known slice so we can assert it reaches run_aura unchanged.
    recent_turns_mock = AsyncMock(return_value=[{"role": "user", "content": "earlier turn"}])
    monkeypatch.setattr(
        "backend.repositories.ChatSessionRepo.recent_turns", recent_turns_mock
    )

    from backend.config import get_settings
    settings = get_settings()

    r = as_user.post(
        "/api/v1/chat",
        json={"message": "now", "session_id": "sess-1"},
    )
    assert r.status_code == 200
    assert captured["history"] == [{"role": "user", "content": "earlier turn"}]
    # Lock-in: recent_turns was called with (session_id, chat_history_turns).
    recent_turns_mock.assert_awaited_once_with("sess-1", settings.chat_history_turns)


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


def test_foreign_analysis_job_not_loaded(as_user, mock_mongo, monkeypatch):
    """I1: analysis owned by a different user must NOT be passed to run_aura.

    When get_owned() returns None (foreign job_id), analysis must stay None
    so the agent uses its no-song-loaded path rather than leaking the data.
    """
    # No sessions → fresh session; no owned analysis.
    mock_mongo.chat_sessions.find_one = AsyncMock(return_value=None)

    captured: dict = {}

    async def _fake_run_aura(*, message, history, analysis, profile, tutor_mode):
        captured["analysis"] = analysis
        return "ok"

    monkeypatch.setattr("backend.main.run_aura", _fake_run_aura)

    # get_owned returns None (caller doesn't own this job).
    monkeypatch.setattr(
        "backend.repositories.AnalysisRepo.get_owned",
        AsyncMock(return_value=None),
    )
    # Ensure there's no public get() fallback by asserting it isn't called.
    get_mock = AsyncMock(return_value={"_id": "job-other", "title": "Secret Song"})
    monkeypatch.setattr("backend.repositories.AnalysisRepo.get", get_mock)

    r = as_user.post(
        "/api/v1/chat",
        json={"message": "hi", "analysis_job_id": "job-other"},
    )
    assert r.status_code == 200
    assert captured["analysis"] is None, "Foreign analysis must not reach the agent"
    get_mock.assert_not_awaited()
