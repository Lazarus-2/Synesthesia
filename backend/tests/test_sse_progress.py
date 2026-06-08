"""Group 8 — disconnect-aware SSE progress stream + dependency wiring."""

from __future__ import annotations

import tomllib
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
    # It exited because of disconnect — no terminal "done"/"error" frame required.
    assert disconnect_after["n"] <= 0


def test_pytest_ini_options_present():
    import tomllib

    data = tomllib.loads((_BACKEND / "pyproject.toml").read_text())
    ini = data["tool"]["pytest"]["ini_options"]
    assert ini["asyncio_mode"] == "auto"
    assert "backend/tests" in ini["testpaths"]
    markers = " ".join(ini["markers"])
    assert "integration" in markers
    assert "ml" in markers


def test_ci_runs_full_suite():
    import yaml

    wf = yaml.safe_load(
        (_BACKEND.parent / ".github" / "workflows" / "test.yml").read_text()
    )
    steps = wf["jobs"]["pytest"]["steps"]
    pytest_step = next(s for s in steps if s.get("name") == "Pytest")
    run = pytest_step["run"]
    # No longer pinned to just the two original files.
    assert "test_graph_routing" in run
    assert "test_chains" in run
    assert "test_api" in run
    assert "test_sse_progress" in run
    # Heavy suites are deselected, not enumerated.
    assert "-m" in run and "not ml and not integration" in run
    # Uses the central pytest config from Task 8.4.
    assert "backend/pyproject.toml" in run
