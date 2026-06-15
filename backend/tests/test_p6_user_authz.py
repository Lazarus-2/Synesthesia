"""Phase 6 G3 — /user/* profile & preference authorization.

These endpoints have no anonymous flow, so they require auth and a caller may
only touch their own id (403 on mismatch, checked before any DB access so a
wrong id can't be used to enumerate valid user_ids).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.auth import UserPrincipal


@pytest.fixture
def client_as(mock_mongo):
    import backend.database as _dbmod

    _dbmod._db = object()
    from backend.auth import require_user
    from backend.database import get_mongodb
    from backend.main import app

    def _make(principal):
        app.dependency_overrides[get_mongodb] = lambda: mock_mongo
        if principal is None:
            app.dependency_overrides.pop(require_user, None)
        else:
            app.dependency_overrides[require_user] = lambda: principal
        return TestClient(app, raise_server_exceptions=False)

    try:
        yield _make
    finally:
        from backend.auth import require_user as _ru
        from backend.database import get_mongodb as _gm

        app.dependency_overrides.pop(_gm, None)
        app.dependency_overrides.pop(_ru, None)


ALICE = UserPrincipal(user_id="alice", username="alice")


class TestPreferencesAuthz:
    def test_unauthenticated_401(self, api_client):
        assert api_client.get("/api/v1/user/alice/preferences").status_code == 401
        assert api_client.put("/api/v1/user/alice/preferences", json={}).status_code == 401

    def test_other_user_403_before_db(self, client_as, mock_mongo):
        mock_mongo.users.find_one = AsyncMock(
            side_effect=AssertionError("403 must precede any DB lookup")
        )
        mock_mongo.users.update_one = AsyncMock(
            side_effect=AssertionError("403 must precede any DB write")
        )
        c = client_as(ALICE)
        assert c.get("/api/v1/user/bob/preferences").status_code == 403
        assert c.put("/api/v1/user/bob/preferences", json={"default_capo": 2}).status_code == 403

    def test_own_preferences_ok(self, client_as, mock_mongo):
        mock_mongo.users.find_one = AsyncMock(
            return_value={"_id": "alice", "instrument": "guitar", "difficulty": "beginner"}
        )
        mock_mongo.users.update_one = AsyncMock()
        c = client_as(ALICE)
        assert c.get("/api/v1/user/alice/preferences").status_code == 200
        assert c.put("/api/v1/user/alice/preferences", json={"default_capo": 2}).status_code == 200


class TestProfileAuthz:
    def test_unauthenticated_401(self, api_client):
        assert api_client.get("/api/v1/user/alice").status_code == 401

    def test_other_user_403_before_db(self, client_as, mock_mongo):
        mock_mongo.users.find_one = AsyncMock(
            side_effect=AssertionError("403 must precede any DB lookup")
        )
        c = client_as(ALICE)
        assert c.get("/api/v1/user/bob").status_code == 403

    def test_own_profile_ok(self, client_as, mock_mongo):
        from datetime import UTC, datetime

        mock_mongo.users.find_one = AsyncMock(
            return_value={
                "_id": "alice",
                "username": "alice",
                "instrument": "guitar",
                "difficulty": "beginner",
                "created_at": datetime.now(UTC),
            }
        )
        c = client_as(ALICE)
        resp = c.get("/api/v1/user/alice")
        assert resp.status_code == 200
        assert resp.json()["id"] == "alice"
