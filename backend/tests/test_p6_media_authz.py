"""Phase 6 G2 — BOLA/ownership on media + analysis read endpoints.

With an authenticated caller, owned resources are gated to the owner (404 on
mismatch — no existence oracle); anonymous resources and the public /share
flow stay readable. Anonymous deployments (no principal) are unchanged.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.auth import UserPrincipal


@pytest.fixture
def client_as(mock_mongo):
    """Factory: TestClient with current_user forced to a given principal (or None)."""
    import backend.database as _dbmod

    _dbmod._db = object()
    from backend.auth import current_user
    from backend.database import get_mongodb
    from backend.main import app

    created = []

    def _make(principal):
        app.dependency_overrides[get_mongodb] = lambda: mock_mongo
        app.dependency_overrides[current_user] = lambda: principal
        c = TestClient(app, raise_server_exceptions=False)
        created.append(c)
        return c

    try:
        yield _make
    finally:
        from backend.auth import current_user as _cu
        from backend.database import get_mongodb as _gm

        app.dependency_overrides.pop(_gm, None)
        app.dependency_overrides.pop(_cu, None)


class TestEnforceOwnedReadHelper:
    async def test_anonymous_caller_is_noop(self, mock_mongo):
        from backend.main import _enforce_owned_read

        mock_mongo.song_analyses.find_one = AsyncMock(
            side_effect=AssertionError("must not query for anonymous caller")
        )
        await _enforce_owned_read("job1", None, mock_mongo)  # no raise, no query

    async def test_owner_allowed(self, mock_mongo):
        from backend.main import _enforce_owned_read

        mock_mongo.song_analyses.find_one = AsyncMock(return_value={"user_id": "A"})
        await _enforce_owned_read("job1", UserPrincipal(user_id="A", username="a"), mock_mongo)

    async def test_other_user_404(self, mock_mongo):
        from fastapi import HTTPException

        from backend.main import _enforce_owned_read

        mock_mongo.song_analyses.find_one = AsyncMock(return_value={"user_id": "A"})
        with pytest.raises(HTTPException) as ei:
            await _enforce_owned_read("job1", UserPrincipal(user_id="B", username="b"), mock_mongo)
        assert ei.value.status_code == 404

    async def test_anonymous_doc_public_to_authed_user(self, mock_mongo):
        from backend.main import _enforce_owned_read

        mock_mongo.song_analyses.find_one = AsyncMock(return_value={"user_id": None})
        await _enforce_owned_read("job1", UserPrincipal(user_id="B", username="b"), mock_mongo)

    async def test_missing_doc_404_by_default(self, mock_mongo):
        from fastapi import HTTPException

        from backend.main import _enforce_owned_read

        mock_mongo.song_analyses.find_one = AsyncMock(return_value=None)
        with pytest.raises(HTTPException):
            await _enforce_owned_read("job1", UserPrincipal(user_id="B", username="b"), mock_mongo)

    async def test_missing_doc_allowed_when_allow_missing(self, mock_mongo):
        from backend.main import _enforce_owned_read

        mock_mongo.song_analyses.find_one = AsyncMock(return_value=None)
        await _enforce_owned_read(
            "job1", UserPrincipal(user_id="B", username="b"), mock_mongo, allow_missing=True
        )


class TestMediaEndpointTraversal:
    @pytest.mark.parametrize("path", [
        "/api/v1/midi/..%2f..%2fetc/full",
        "/api/v1/stems/..%2f..%2fetc/vocals",
        "/api/v1/audio/..%2f..%2fetc",
    ])
    def test_traversal_job_id_rejected(self, client_as, path):
        c = client_as(None)
        resp = c.get(path)
        # Decoded ".." path is rejected (404), never escapes the storage dir.
        assert resp.status_code in (404, 400)


class TestMidiSymlinkGuard:
    def test_full_branch_rejects_symlink_escaping_upload_dir(
        self, client_as, mock_mongo, tmp_path, monkeypatch
    ):
        from backend.config import get_settings

        settings = get_settings()
        upload = tmp_path / "uploads"
        upload.mkdir()
        monkeypatch.setattr(settings, "audio_upload_dir", upload, raising=False)
        # A staged file for the job is actually a symlink to a file OUTSIDE the
        # upload dir — the resolve().relative_to guard must reject it.
        outside = tmp_path / "secret.wav"
        outside.write_bytes(b"RIFFsecret")
        (upload / "symjob_song.wav").symlink_to(outside)

        mock_mongo.song_analyses.find_one = AsyncMock(return_value={"user_id": None})
        c = client_as(None)
        resp = c.get("/api/v1/midi/symjob/full")
        assert resp.status_code == 404


class TestAudioOwnership:
    def test_other_user_gets_404_on_owned_audio(self, client_as, mock_mongo):
        mock_mongo.song_analyses.find_one = AsyncMock(return_value={"_id": "job1", "user_id": "A"})
        c = client_as(UserPrincipal(user_id="B", username="b"))
        resp = c.get("/api/v1/audio/job1")
        assert resp.status_code == 404

    def test_anonymous_audio_served_to_public(self, client_as, mock_mongo, tmp_path, monkeypatch):
        # Anonymous doc + a real audio file -> token-less caller (share player) gets it.
        from backend.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "audio_upload_dir", tmp_path, raising=False)
        (tmp_path / "job1_song.mp3").write_bytes(b"ID3fakeaudio")
        mock_mongo.song_analyses.find_one = AsyncMock(return_value={"_id": "job1", "user_id": None})
        c = client_as(None)  # anonymous / public
        resp = c.get("/api/v1/audio/job1")
        assert resp.status_code == 200
