"""FT-03: progress and result live under distinct Redis keys (Group 4 step d).

Drives the real HybridJobStore against a patched async cache so we can assert
the exact keys written.
"""

from __future__ import annotations

import json

import pytest

from backend.services import job_store as js_mod


@pytest.fixture
def patched_cache(monkeypatch):
    store: dict[str, str] = {}

    class _AsyncCache:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ttl_seconds=1800):
            store[key] = value
            return True

    monkeypatch.setattr(js_mod, "cache", _AsyncCache())
    return store


@pytest.mark.asyncio
async def test_progress_and_result_use_distinct_keys(patched_cache):
    store = patched_cache
    js = js_mod.HybridJobStore()

    await js.set_progress("job-1", {"status": "running", "progress": 40})
    await js.cache_response("job-1", json.dumps({"status": "done"}))

    assert "song:analysis:job-1:progress" in store
    assert "song:analysis:job-1:result" in store
    # cache_response no longer clobbers progress.
    assert json.loads(store["song:analysis:job-1:progress"])["progress"] == 40
    assert json.loads(store["song:analysis:job-1:result"])["status"] == "done"


@pytest.mark.asyncio
async def test_get_cached_response_reads_result_key(patched_cache):
    js = js_mod.HybridJobStore()
    await js.cache_response("job-2", json.dumps({"status": "done", "title": "T"}))

    got = await js.get_cached_response("job-2")
    assert got is not None
    assert json.loads(got)["title"] == "T"


@pytest.mark.asyncio
async def test_get_progress_reads_progress_key(patched_cache):
    js = js_mod.HybridJobStore()
    await js.set_progress("job-3", {"status": "running", "progress": 10})
    prog = await js.get_progress("job-3")
    assert prog == {"status": "running", "progress": 10}


@pytest.mark.asyncio
async def test_is_stale_false_without_heartbeat(patched_cache):
    js = js_mod.HybridJobStore()
    assert await js.is_stale("job-never") is False
