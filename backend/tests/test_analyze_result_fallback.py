"""GET /analyze/{job_id}: serve cached :result, else fall back to Mongo (FT-03)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


def _minimal_analyze_json(job_id: str) -> str:
    """A valid AnalyzeResponse JSON body the endpoint can re-emit verbatim."""
    from backend.schemas import AnalyzeResponse

    return AnalyzeResponse(
        job_id=job_id,
        status="done",
        analysis=None,
        instrument_guide=None,
    ).model_dump_json()


def test_analyze_serves_cached_result(api_client):
    job_id = "job-cached"
    cached_json = _minimal_analyze_json(job_id)

    async def fake_get_cached(jid):
        assert jid == job_id
        return cached_json

    with patch(
        "backend.main.get_job_store",
        return_value=type(
            "S",
            (),
            {"get_cached_response": staticmethod(AsyncMock(side_effect=fake_get_cached))},
        )(),
    ):
        resp = api_client.get(f"/api/v1/analyze/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == job_id


def test_analyze_falls_back_to_mongo_on_cache_miss(api_client, mock_mongo):
    job_id = "job-mongo"
    mock_mongo.song_analyses.find_one = AsyncMock(
        return_value={
            "_id": job_id,
            "title": "Mongo Song",
            "artist": "DB",
            "duration": 100.0,
            "key": "C major",
            "tempo": 120.0,
            "time_signature": "4/4",
            "chords": [],
            "beats": [],
            "sections": [],
            "roman": None,
            "vibe_palette": [],
            "theory_explanation": "x",
            "instrument_guides": {},
        }
    )

    miss_store = type(
        "S",
        (),
        {
            "get_cached_response": staticmethod(AsyncMock(return_value=None)),
            "cache_response": staticmethod(AsyncMock()),
        },
    )()
    with patch("backend.main.get_job_store", return_value=miss_store):
        resp = api_client.get(f"/api/v1/analyze/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["analysis"]["title"] == "Mongo Song"
    mock_mongo.song_analyses.find_one.assert_awaited_once_with({"_id": job_id})
