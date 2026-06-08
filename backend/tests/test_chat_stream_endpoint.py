"""POST /chat/stream — SSE frames over stream_aura (Group D.6).

stream_aura is monkeypatched to a scripted async generator of ServerSentEvent
frames, so no model runs. We assert the wire carries context + chunk + done
and that the assistant turn is persisted after the stream drains.
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


def test_stream_unauthenticated_is_401(api_client):
    r = api_client.post("/api/v1/chat/stream", json={"message": "hi"})
    assert r.status_code == 401
