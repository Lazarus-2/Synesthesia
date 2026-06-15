"""Phase 6 G1 — ownership resolver + identity binding.

resolve_readable is the single ownership rule shared by every analysis-keyed
media/read endpoint; these unit tests pin its matrix so the endpoint tests in
G2 can trust it. POST /user + POST /analyze identity binding are exercised via
the API client.
"""

from __future__ import annotations

import pytest

from backend.auth import UserPrincipal
from backend.repositories.analysis_repo import AnalysisRepo


class _FakeColl:
    def __init__(self, docs: dict[str, dict]):
        self._docs = docs

    async def find_one(self, query):
        # Supports {"_id": x} and {"_id": x, "user_id": y} like motor.
        doc = self._docs.get(query.get("_id"))
        if doc is None:
            return None
        if "user_id" in query and doc.get("user_id") != query["user_id"]:
            return None
        return doc


def _repo(docs):
    repo = AnalysisRepo.__new__(AnalysisRepo)
    repo._coll = _FakeColl(docs)
    return repo


DOCS = {
    "anon": {"_id": "anon", "user_id": None, "title": "Anon"},
    "owned_a": {"_id": "owned_a", "user_id": "A", "title": "A's"},
    "owned_b": {"_id": "owned_b", "user_id": "B", "title": "B's"},
}


class TestResolveReadable:
    @pytest.mark.parametrize(
        "job,requester,expected",
        [
            # anonymous doc: readable by everyone
            ("anon", None, "anon"),
            ("anon", "A", "anon"),
            ("anon", "B", "anon"),
            # owned-by-A: only A
            ("owned_a", "A", "owned_a"),
            ("owned_a", "B", None),
            ("owned_a", None, None),
            # owned-by-B: only B
            ("owned_b", "B", "owned_b"),
            ("owned_b", "A", None),
            # missing doc
            ("nope", "A", None),
            ("nope", None, None),
        ],
    )
    async def test_matrix(self, job, requester, expected):
        repo = _repo(DOCS)
        doc = await repo.resolve_readable(job, requester)
        assert (doc["_id"] if doc else None) == expected


@pytest.fixture
def as_user(mock_mongo):
    """TestClient with require_user forced to a fixed principal (mirrors chat tests)."""
    import backend.database as _dbmod

    _dbmod._db = object()
    from fastapi.testclient import TestClient

    from backend.auth import require_user
    from backend.database import get_mongodb
    from backend.main import app

    app.dependency_overrides[get_mongodb] = lambda: mock_mongo
    app.dependency_overrides[require_user] = lambda: UserPrincipal(
        user_id="attacker", username="attacker"
    )
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_mongodb, None)
        app.dependency_overrides.pop(require_user, None)


class TestPostUserIdentityBinding:
    def test_post_user_requires_auth(self, api_client):
        # Default config: no token -> 401 (was an unauthenticated overwrite).
        resp = api_client.post("/api/v1/user", json={"id": "victim", "username": "x"})
        assert resp.status_code == 401

    def test_post_user_rejects_body_id_for_another_user(self, as_user, mock_mongo):
        from unittest.mock import AsyncMock

        mock_mongo.users.update_one = AsyncMock()
        mock_mongo.users.replace_one = AsyncMock()
        # Attacker (token=attacker) tries to target victim's row by body id.
        resp = as_user.post("/api/v1/user", json={"id": "victim", "username": "pwned"})
        assert resp.status_code == 403
        mock_mongo.users.update_one.assert_not_awaited()
        mock_mongo.users.replace_one.assert_not_awaited()

    def test_post_user_self_update_binds_to_token_and_uses_set(self, as_user, mock_mongo):
        from unittest.mock import AsyncMock

        captured = {}

        async def fake_update_one(flt, update, upsert=False):
            captured["filter"] = flt
            captured["update"] = update

            class R:
                matched_count = 1
                upserted_id = None

            return R()

        mock_mongo.users.update_one = AsyncMock(side_effect=fake_update_one)
        mock_mongo.users.replace_one = AsyncMock(
            side_effect=AssertionError("must not use replace_one (clobbers password_hash)")
        )

        # No body id (or own id) -> bound to the token, $set on own row.
        resp = as_user.post("/api/v1/user", json={"username": "newname"})
        assert resp.status_code == 200
        assert captured["filter"]["_id"] == "attacker"
        assert "$set" in captured["update"]
        assert "password_hash" not in captured["update"]["$set"]
