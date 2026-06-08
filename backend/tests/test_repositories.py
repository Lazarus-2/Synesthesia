"""Tests for the async repository layer + user_id ownership (Group 5 / ID-01).

Repos are thin async wrappers over Motor collections. Tests drive them with
the ``mock_mongo`` fixture from conftest.py so they stay hermetic — no live
Mongo, no network. The fixture's collections expose ``find_one``,
``insert_one``, ``update_one``, ``replace_one`` as AsyncMocks and ``find`` as
a self-chaining async-iterable.
"""

from __future__ import annotations

import pytest

from backend.models import SongAnalysisModel


class TestSongAnalysisUserId:
    def test_user_id_defaults_to_none(self):
        song = SongAnalysisModel(
            id="job_1", duration=10.0, key="C major", tempo=120.0
        )
        assert song.user_id is None

    def test_user_id_round_trips(self):
        song = SongAnalysisModel(
            id="job_2", duration=10.0, key="C major", tempo=120.0, user_id="usr_9"
        )
        assert song.user_id == "usr_9"
        assert song.model_dump()["user_id"] == "usr_9"
