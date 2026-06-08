"""POST /chat/stream — SSE frames over stream_aura (Group D.6).

stream_aura is monkeypatched to a scripted async generator of ServerSentEvent
frames, so no model runs. We assert the wire carries context + chunk + done
and that persistence behaves correctly under both clean drain and mid-stream
error scenarios.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest
from sse_starlette.sse import ServerSentEvent

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


def test_stream_emits_context_chunk_done(as_user, monkeypatch):
    async def _fake_stream(**kwargs):
        yield ServerSentEvent(event="context", data='{"title":"Test Song"}')
        yield ServerSentEvent(event="chunk", data='{"text":"Hel"}')
        yield ServerSentEvent(event="chunk", data='{"text":"lo"}')
        yield ServerSentEvent(event="done", data='{"reply_length":5}')

    monkeypatch.setattr("backend.main.stream_aura", _fake_stream)

    with as_user.stream(
        "POST", "/api/v1/chat/stream", json={"message": "hi"}
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(chunk for chunk in r.iter_text())

    assert "event: context" in body
    assert "event: chunk" in body
    assert "event: done" in body
    assert "Hel" in body and "lo" in body


def test_stream_recent_turns_supplies_history(as_user, mock_mongo, monkeypatch):
    """recent_turns must be the call that supplies the agent's history — lock-in."""
    mock_mongo.chat_sessions.find_one = AsyncMock(
        return_value={"_id": "sess-1", "user_id": "user-1", "messages": []}
    )

    recent_turns_mock = AsyncMock(return_value=[{"role": "user", "content": "old"}])
    monkeypatch.setattr(
        "backend.repositories.ChatSessionRepo.recent_turns", recent_turns_mock
    )

    captured: dict = {}

    async def _fake_stream(*, message, history, **kwargs):
        captured["history"] = history
        yield ServerSentEvent(event="done", data='{}')

    monkeypatch.setattr("backend.main.stream_aura", _fake_stream)

    from backend.config import get_settings
    settings = get_settings()

    with as_user.stream(
        "POST", "/api/v1/chat/stream", json={"message": "hi", "session_id": "sess-1"}
    ) as r:
        list(r.iter_text())

    assert captured["history"] == [{"role": "user", "content": "old"}]
    recent_turns_mock.assert_awaited_once_with("sess-1", settings.chat_history_turns)


def test_stream_persists_assistant_turn(as_user, monkeypatch):
    appended: list[tuple] = []

    async def _append(self, session_id, role, content, user_id=None):
        appended.append((role, content))

    monkeypatch.setattr(
        "backend.repositories.ChatSessionRepo.append_turn", _append
    )

    async def _fake_stream(**kwargs):
        yield ServerSentEvent(event="chunk", data='{"text":"Hi there"}')
        yield ServerSentEvent(event="done", data='{"reply_length":7}')

    monkeypatch.setattr("backend.main.stream_aura", _fake_stream)

    with as_user.stream(
        "POST", "/api/v1/chat/stream", json={"message": "yo"}
    ) as r:
        list(r.iter_text())  # drain so the generator's finally runs

    roles = [role for role, _ in appended]
    assert "user" in roles and "assistant" in roles


def test_stream_mid_error_persists_user_and_partial_assistant(as_user, monkeypatch):
    """I2: a stream_aura that raises mid-stream must still persist the user
    turn (written before the loop) and any partial assistant text accumulated
    before the error."""
    appended: list[tuple] = []

    async def _append(self, session_id, role, content, user_id=None):
        appended.append((role, content))

    monkeypatch.setattr(
        "backend.repositories.ChatSessionRepo.append_turn", _append
    )

    async def _fake_stream_raises(**kwargs):
        yield ServerSentEvent(event="chunk", data='{"text":"Part"}')
        raise RuntimeError("mid-stream boom")
        yield  # pragma: no cover — makes this an async generator

    monkeypatch.setattr("backend.main.stream_aura", _fake_stream_raises)

    with as_user.stream(
        "POST", "/api/v1/chat/stream", json={"message": "yo"}
    ) as r:
        body = "".join(r.iter_text())

    # The error SSE frame must be present
    assert "CHAT_STREAM_FAILED" in body

    roles = [role for role, _ in appended]
    # User turn was persisted before the stream started.
    assert "user" in roles
    # Partial assistant text ("Part") was persisted in the except branch.
    assert "assistant" in roles
    assistant_content = next(c for r2, c in appended if r2 == "assistant")
    assert "Part" in assistant_content


def test_stream_unauthenticated_is_401(api_client):
    r = api_client.post("/api/v1/chat/stream", json={"message": "hi"})
    assert r.status_code == 401


def test_stream_foreign_session_is_403(as_user, mock_mongo, monkeypatch):
    """A session_id owned by a different user must be rejected with 403."""
    mock_mongo.chat_sessions.find_one = AsyncMock(
        return_value={"_id": "sess-foreign", "user_id": "user-999"}
    )

    async def _fake_stream(**kwargs):  # pragma: no cover
        raise AssertionError("stream must not start on 403")
        yield  # pragma: no cover

    monkeypatch.setattr("backend.main.stream_aura", _fake_stream)

    r = as_user.post(
        "/api/v1/chat/stream",
        json={"message": "hi", "session_id": "sess-foreign"},
    )
    assert r.status_code == 403


def test_stream_foreign_analysis_not_loaded(as_user, mock_mongo, monkeypatch):
    """I1: analysis owned by a different user must NOT be passed to stream_aura."""
    mock_mongo.chat_sessions.find_one = AsyncMock(return_value=None)

    captured: dict = {}

    async def _fake_stream(*, message, history, analysis, **kwargs):
        captured["analysis"] = analysis
        yield ServerSentEvent(event="done", data='{}')

    monkeypatch.setattr("backend.main.stream_aura", _fake_stream)

    from backend.repositories import AnalysisRepo
    monkeypatch.setattr(
        "backend.repositories.AnalysisRepo.get_owned",
        AsyncMock(return_value=None),
    )
    get_mock = AsyncMock(return_value={"_id": "job-other", "title": "Secret Song"})
    monkeypatch.setattr("backend.repositories.AnalysisRepo.get", get_mock)

    with as_user.stream(
        "POST", "/api/v1/chat/stream",
        json={"message": "hi", "analysis_job_id": "job-other"},
    ) as r:
        list(r.iter_text())

    assert captured["analysis"] is None, "Foreign analysis must not reach stream_aura"
    get_mock.assert_not_awaited()
