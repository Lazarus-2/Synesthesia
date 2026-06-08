"""Group 8 — disconnect-aware SSE progress stream + dependency wiring."""

from __future__ import annotations

import tomllib
import yaml  # m1: import at module level (not inside test body)
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]


def test_sse_starlette_declared_in_pyproject():
    data = tomllib.loads((_BACKEND / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    assert any(d.startswith("sse-starlette") for d in deps), deps


def test_sse_starlette_declared_in_requirements():
    lines = (_BACKEND / "requirements.txt").read_text().splitlines()
    assert any(line.startswith("sse-starlette") for line in lines), lines


def test_sse_starlette_importable():
    from sse_starlette.sse import EventSourceResponse

    assert EventSourceResponse is not None


import asyncio
import inspect

import pytest


@pytest.mark.asyncio
async def test_progress_endpoint_returns_event_source_response(monkeypatch):
    """The endpoint must return an EventSourceResponse, not StreamingResponse."""
    from sse_starlette.sse import EventSourceResponse

    import backend.main as main

    class _Store:
        def get_cached_response(self, job_id):  # never terminal
            return None

        def is_stale(self, job_id, *, timeout_s=0):
            return False

    monkeypatch.setattr(main, "get_job_store", lambda: _Store())

    class _Req:
        async def is_disconnected(self):
            return True

    resp = await main.get_analysis_progress("job-xyz", _Req())
    assert isinstance(resp, EventSourceResponse)


@pytest.mark.asyncio
async def test_progress_generator_stops_on_disconnect(monkeypatch):
    """The generator must terminate promptly once the client disconnects."""
    import backend.main as main

    class _Store:
        # Always pending — without the disconnect check this loops for 30 min.
        def get_cached_response(self, job_id):
            return None

        def is_stale(self, job_id, *, timeout_s=0):
            return False

    monkeypatch.setattr(main, "get_job_store", lambda: _Store())
    # Don't actually sleep 1s per tick. Capture the real ``asyncio.sleep``
    # first: ``main.asyncio is asyncio`` (same module object), so the stub
    # must delegate to the captured original rather than the now-patched
    # name, or it would recurse into itself.
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(main.asyncio, "sleep", lambda _s: _real_sleep(0))

    disconnect_after = {"n": 2}

    class _Req:
        async def is_disconnected(self):
            disconnect_after["n"] -= 1
            return disconnect_after["n"] <= 0

    resp = await main.get_analysis_progress("job-abc", _Req())
    gen = resp.body_iterator
    assert inspect.isasyncgen(gen)

    # Drain with a hard timeout; a non-disconnect-aware generator would hang.
    frames = []

    async def _drain():
        async for frame in gen:
            frames.append(frame)

    await asyncio.wait_for(_drain(), timeout=2.0)
    # m3: tighten assertion — the counter was decremented exactly 2 times and
    # the loop exited on the second decrement (disconnect_after["n"] == 0).
    assert disconnect_after["n"] == 0


@pytest.mark.asyncio
async def test_progress_generator_done_path_emits_done_frame_and_exits(monkeypatch):
    """I3/I4: when the result is already 'done' on first poll the generator must
    emit exactly one frame with event=='done' and then return (no infinite loop).

    This locks the SSE wire format: a regression that emits 'chunk' instead of
    'done', or that keeps looping after a terminal frame, will fail this test.
    """
    import json

    from sse_starlette.sse import ServerSentEvent

    import backend.main as main

    done_payload = json.dumps({"job_id": "job-done", "status": "done", "analysis": {}})

    class _Store:
        def get_cached_response(self, job_id):
            # Returns the terminal payload immediately on first poll.
            return done_payload

        def is_stale(self, job_id, *, timeout_s=0):
            # Should never be called when job_finished=True — C1 guard.
            raise AssertionError("is_stale must not be called for a finished job")

    monkeypatch.setattr(main, "get_job_store", lambda: _Store())

    _real_sleep = asyncio.sleep
    monkeypatch.setattr(main.asyncio, "sleep", lambda _s: _real_sleep(0))

    class _Req:
        async def is_disconnected(self):
            return False  # client stays connected; generator must exit on done

    resp = await main.get_analysis_progress("job-done", _Req())
    gen = resp.body_iterator

    frames = []

    async def _drain():
        async for frame in gen:
            frames.append(frame)

    await asyncio.wait_for(_drain(), timeout=2.0)

    # I3: assert each emitted frame has non-empty .data
    for frame in frames:
        if isinstance(frame, ServerSentEvent):
            assert frame.data, f"SSE frame missing .data: {frame!r}"

    # I4: assert the terminal frame has event == "done"
    sse_frames = [f for f in frames if isinstance(f, ServerSentEvent)]
    assert sse_frames, "Expected at least one SSE frame"
    done_frames = [f for f in sse_frames if f.event == "done"]
    assert done_frames, f"Expected a frame with event='done'; got events: {[f.event for f in sse_frames]}"

    # Generator must have exited — only one done frame expected.
    assert len(done_frames) == 1


def test_pytest_ini_options_present():
    data = tomllib.loads((_BACKEND / "pyproject.toml").read_text())
    ini = data["tool"]["pytest"]["ini_options"]
    assert ini["asyncio_mode"] == "auto"
    # m2: testpaths must now be ["tests"] (relative to backend/ rootdir when
    # invoked with -c backend/pyproject.toml) — not the old "backend/tests".
    assert "tests" in ini["testpaths"]
    assert "backend/tests" not in ini["testpaths"], (
        "testpaths must be 'tests' (relative to backend/ rootdir), not 'backend/tests'"
    )
    markers = " ".join(ini["markers"])
    assert "integration" in markers
    assert "ml" in markers


def test_ci_runs_full_suite():
    wf = yaml.safe_load(
        (_BACKEND.parent / ".github" / "workflows" / "test.yml").read_text()
    )
    steps = wf["jobs"]["pytest"]["steps"]
    pytest_step = next(s for s in steps if s.get("name") == "Pytest")
    run = pytest_step["run"]
    # CI now runs the whole directory (not an enumerated file list) so new
    # test files are never silently skipped.
    assert "backend/tests" in run
    # Heavy suites are deselected by marker, not excluded by omission.
    assert "-m" in run and "not ml and not integration" in run
    # Uses the central pytest config from Task 8.4.
    assert "backend/pyproject.toml" in run
    # Verify it is NOT an enumerated file list (would need individual file names).
    # The directory form doesn't contain individual file names like test_chains.py
    # at the pytest invocation level — they live under the directory path.
    assert "test_graph_routing.py" not in run, (
        "CI should run the whole directory, not enumerate individual files"
    )
