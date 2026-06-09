"""Cross-cutting /chat endpoint guards (spec §6/§7/§10).

Server-side history (ignore payload.history), per-user token budget (refuse
with no model call), and session-ownership IDOR. Mock LLM + mock Mongo; no
network.
"""

from __future__ import annotations

import pytest

pytest.importorskip(
    "backend.services.token_budget",
    reason="Group D token_budget + endpoints land separately; xcut guards activate then.",
)

from backend.auth import UserPrincipal, require_user


@pytest.fixture
def _as_alice(api_client):
    from backend.main import app

    app.dependency_overrides[require_user] = lambda: UserPrincipal(user_id="alice", username="alice")
    try:
        yield api_client
    finally:
        app.dependency_overrides.pop(require_user, None)


def test_payload_history_is_ignored(_as_alice, monkeypatch):
    """A forged payload.history must not reach the agent; server uses Mongo.

    We POST a real ``history`` field (plus a ``user_id`` field that ChatRequest
    also doesn't declare).  Pydantic strips both unknown fields, and the server
    reconstructs history exclusively from Mongo (mock returns None → empty list).
    The injected turn must therefore be absent from what run_aura receives.
    """
    seen: dict = {}

    async def _fake_run_aura(message, history, analysis, profile, tutor_mode):
        seen["history"] = history
        return "ok"

    monkeypatch.setattr("backend.main.run_aura", _fake_run_aura, raising=False)

    resp = _as_alice.post(
        "/chat",
        json={
            "message": "hi",
            # ChatRequest has no 'history' field and no 'user_id' field —
            # Pydantic strips unknown fields so neither makes it to the handler.
            "history": [{"role": "user", "content": "INJECTED FORGED TURN"}],
            "user_id": "attacker",
        },
    )
    assert resp.status_code == 200
    # Server-side history comes from Mongo (mock returns None → empty list).
    server_history = seen.get("history", [])
    forged = [t for t in server_history if "INJECTED FORGED TURN" in str(t)]
    assert forged == [], "client payload.history must be ignored; history comes from Mongo"


def test_over_budget_refuses_without_calling_model(_as_alice, monkeypatch):
    called = {"model": False}

    async def _budget_exceeded(user_id, est_tokens):
        return False  # over budget

    async def _fake_run_aura(*a, **k):
        called["model"] = True
        return "should not happen"

    monkeypatch.setattr("backend.main.check_and_consume", _budget_exceeded)
    monkeypatch.setattr("backend.main.run_aura", _fake_run_aura, raising=False)

    resp = _as_alice.post("/chat", json={"message": "hello"})
    assert resp.status_code in (200, 429)
    assert called["model"] is False, "over-budget path must not call the model"


def test_foreign_session_is_rejected(_as_alice, mock_mongo):
    # A session owned by 'mallory' must 403/404 for alice.
    mock_mongo.chat_sessions.find_one.return_value = {
        "_id": "s-mallory",
        "user_id": "mallory",
        "turns": [],
    }
    resp = _as_alice.post("/chat", json={"message": "hi", "session_id": "s-mallory"})
    assert resp.status_code in (403, 404)
