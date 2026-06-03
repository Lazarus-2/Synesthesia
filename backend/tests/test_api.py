"""End-to-end API tests via FastAPI TestClient (Plan 3 D4).

Cover the route surface that doesn't require live ML / LLM / Mongo:

  * /health and /health/ready
  * The standard APIError envelope on 404 / 422
  * Both /api/v1/* and legacy unprefixed mounts
  * Auth round-trip (signup, login, /me)
  * Library + share with mocked Mongo

Tests use the ``api_client`` and ``mock_mongo`` fixtures from conftest.py
so the setup is hermetic and quick.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def _auth_env():
    """Ensure the JWT secret is set so signup/login don't 503 in tests."""
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


class TestHealth:
    def test_liveness(self, api_client):
        r = api_client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_readiness_ok_when_deps_up(self, api_client, mock_mongo):
        mock_mongo.command = AsyncMock(return_value={"ok": 1})
        r = api_client.get("/health/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "mongodb" in body["checks"]
        assert "redis" in body["checks"]

    def test_readiness_degraded_when_mongo_down(self, api_client, mock_mongo):
        mock_mongo.command = AsyncMock(side_effect=RuntimeError("conn refused"))
        r = api_client.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "degraded"
        assert body["checks"]["mongodb"]["ok"] is False


class TestErrorEnvelope:
    def test_404_uses_apierror_envelope(self, api_client):
        r = api_client.get("/route/does/not/exist")
        assert r.status_code == 404
        body = r.json()
        assert body["status"] == "error"
        assert body["code"] == "NOT_FOUND"

    def test_validation_error_envelope(self, api_client):
        # Sending invalid body to a route that expects ChatRequest.
        r = api_client.post("/api/v1/chat", json={"history": "not-a-list"})
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "errors" in body["details"]

    def test_analyze_400_for_no_input(self, api_client):
        r = api_client.post("/api/v1/analyze", data={"instrument": "guitar"})
        assert r.status_code == 400
        body = r.json()
        assert body["code"] == "BAD_REQUEST"


class TestVersionedRouting:
    def test_versioned_route_works(self, api_client):
        r = api_client.get("/api/v1/user/u-nope")
        assert r.status_code == 404
        assert r.json()["code"] == "NOT_FOUND"

    def test_legacy_alias_works(self, api_client):
        r = api_client.get("/user/u-nope")
        assert r.status_code == 404

    def test_openapi_includes_both_mounts(self, api_client):
        spec = api_client.get("/openapi.json").json()
        paths = set(spec["paths"].keys())
        assert "/health" in paths
        assert "/api/v1/analyze" in paths
        # Legacy alias is still present until the frontend fully migrates.
        assert "/analyze" in paths


class TestAuth:
    def test_signup_login_me_roundtrip(self, api_client, mock_mongo):
        state: dict = {}

        async def find(q):
            return state.get(q.get("username") or q.get("_id"))

        async def insert(doc):
            state[doc["username"]] = doc
            state[doc["_id"]] = doc

        mock_mongo.users.find_one = AsyncMock(side_effect=find)
        mock_mongo.users.insert_one = AsyncMock(side_effect=insert)

        # Sign up
        r = api_client.post(
            "/api/v1/auth/signup",
            json={"username": "alice", "password": "hunter2x9!"},
        )
        assert r.status_code == 200, r.json()
        body = r.json()
        token = body["token"]
        assert body["username"] == "alice"

        # Login
        r = api_client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "hunter2x9!"},
        )
        assert r.status_code == 200

        # /me with token
        r = api_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["user"]["username"] == "alice"

        # /me anonymous
        r = api_client.get("/api/v1/auth/me")
        assert r.json() == {"user": None}

    def test_signup_rejects_weak_password(self, api_client, mock_mongo):
        mock_mongo.users.find_one = AsyncMock(return_value=None)
        r = api_client.post(
            "/api/v1/auth/signup",
            json={"username": "bob", "password": "short"},
        )
        assert r.status_code == 400

    def test_login_invalid_credentials_401(self, api_client, mock_mongo):
        mock_mongo.users.find_one = AsyncMock(return_value=None)
        r = api_client.post(
            "/api/v1/auth/login",
            json={"username": "x", "password": "y"},
        )
        assert r.status_code == 401


class TestLibrary:
    def test_library_empty(self, api_client, mock_mongo):
        mock_mongo.song_analyses.count_documents = AsyncMock(return_value=0)
        r = api_client.get("/api/v1/library")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_library_clamps_limit(self, api_client, mock_mongo):
        mock_mongo.song_analyses.count_documents = AsyncMock(return_value=0)
        # Asking for a huge limit shouldn't 500.
        r = api_client.get("/api/v1/library?limit=999&offset=0")
        assert r.status_code == 200
        assert r.json()["limit"] <= 100


class TestShare:
    def test_share_404_when_unknown(self, api_client, mock_mongo):
        mock_mongo.song_analyses.find_one = AsyncMock(return_value=None)
        r = api_client.get("/api/v1/share/missing-id")
        assert r.status_code == 404

    def test_share_returns_analysis_when_found(self, api_client, mock_mongo):
        mock_mongo.song_analyses.find_one = AsyncMock(
            return_value={
                "_id": "abc",
                "title": "Demo",
                "artist": "Test",
                "duration": 60.0,
                "key": "C major",
                "tempo": 120.0,
                "time_signature": "4/4",
                "chords": [
                    {"start": 0.0, "end": 2.0, "chord": "C", "confidence": 1.0, "color": "#FF0000"},
                ],
                "beats": [],
                "sections": [],
                "roman": None,
                "vibe_palette": ["#FF0000"],
                "theory_explanation": None,
                "instrument_guides": {},
                "stems": {},
            }
        )
        r = api_client.get("/api/v1/share/abc")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "done"
        assert body["analysis"]["title"] == "Demo"
        assert body["audio_url"] == "/api/v1/audio/abc"


class TestPreferences:
    def test_get_preferences_404_for_unknown_user(self, api_client, mock_mongo):
        mock_mongo.users.find_one = AsyncMock(return_value=None)
        r = api_client.get("/api/v1/user/nope/preferences")
        assert r.status_code == 404

    def test_put_preferences_upserts(self, api_client, mock_mongo):
        r = api_client.put(
            "/api/v1/user/u1/preferences",
            json={"default_instrument": "piano", "default_capo": 3},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["default_instrument"] == "piano"
        assert body["default_capo"] == 3
        mock_mongo.users.update_one.assert_called_once()


# ---------------------------------------------------------------------------
# /analyze preflight URL validation (Plan 3 live-test report 2)
# ---------------------------------------------------------------------------


class TestAnalyzeUrlValidation:
    """Synchronous URL validation at the /analyze endpoint.

    Used to be: caller submits ``youtube_url="/path/to/local.wav"``, the
    request gets a 200 with a queued job, the worker tries to ingest it,
    LangGraph eventually crashes with a recursion error and the user sees
    "Analysis pipeline crashed" 30s later. Now: same caller gets a clean
    400 + standard APIError envelope synchronously.
    """

    def test_local_path_typed_as_url_rejected_with_400(
        self,
        api_client,
        mock_mongo,
    ):
        mock_mongo.song_analyses.find_one = AsyncMock(return_value=None)
        r = api_client.post(
            "/api/v1/analyze",
            data={
                "youtube_url": "/home/janit/test.wav",
                "instrument": "guitar",
                "difficulty": "beginner",
            },
        )
        assert r.status_code == 400
        body = r.json()
        assert body["code"] == "BAD_REQUEST"
        assert "Invalid URL" in body["message"]

    def test_bogus_string_rejected(self, api_client, mock_mongo):
        mock_mongo.song_analyses.find_one = AsyncMock(return_value=None)
        r = api_client.post(
            "/api/v1/analyze",
            data={
                "youtube_url": "not-a-url-at-all",
                "instrument": "guitar",
                "difficulty": "beginner",
            },
        )
        assert r.status_code == 400
        assert "Invalid URL" in r.json()["message"]

    def test_non_youtube_https_url_rejected(self, api_client, mock_mongo):
        mock_mongo.song_analyses.find_one = AsyncMock(return_value=None)
        r = api_client.post(
            "/api/v1/analyze",
            data={
                "youtube_url": "https://example.com/song.mp3",
                "instrument": "guitar",
                "difficulty": "beginner",
            },
        )
        assert r.status_code == 400
        assert "Host not allowed" in r.json()["message"]

    def test_file_scheme_rejected(self, api_client, mock_mongo):
        mock_mongo.song_analyses.find_one = AsyncMock(return_value=None)
        r = api_client.post(
            "/api/v1/analyze",
            data={
                "youtube_url": "file:///etc/passwd",
                "instrument": "guitar",
                "difficulty": "beginner",
            },
        )
        assert r.status_code == 400
        assert "scheme" in r.json()["message"].lower()

    def test_neither_url_nor_file_returns_400(self, api_client, mock_mongo):
        del mock_mongo  # unused; explicit to silence the lint hint
        r = api_client.post(
            "/api/v1/analyze",
            data={"instrument": "guitar", "difficulty": "beginner"},
        )
        assert r.status_code == 400
        assert "Provide either" in r.json()["message"]
