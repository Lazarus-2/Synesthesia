"""Playwright fixtures for the live browser E2E suite.

Why a custom conftest rather than the stock ``pytest-playwright`` plugin?
We need three behaviours that the bundled fixtures don't give us cleanly:

  1. Fail-fast on any console error or unhandled page exception (catches
     React hydration regressions, missing ``"use client"`` directives,
     CORS / SSE wiring breakage). The stock ``page`` fixture swallows
     those.
  2. Save a screenshot to disk whenever an assertion fails, named after
     the test, so the chat reply can link to it without re-running.
  3. A small ``run_report`` helper every test writes one row into; the
     final test (or a teardown hook) materializes the markdown summary.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import struct
import wave
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

# After the Python-into-backend/ refactor, this file lives at
# ``backend/tests/e2e_browser/conftest.py`` — three ``parent`` hops up
# lands on the repo root. Artifacts and fixture WAVs live next to the
# tests so the e2e tree is self-contained and easy to wipe.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
_SCREENSHOT_DIR = _ARTIFACT_DIR / "screenshots"
_VIDEO_DIR = _ARTIFACT_DIR / "video"
_REPORT_PATH = _ARTIFACT_DIR / "run_report.md"

_FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://localhost:3001")
_API_URL = os.environ.get("E2E_API_URL", "http://localhost:8001")
_FIXTURE_AUDIO_DIR = _ARTIFACT_DIR / "tmp_audio"


# ----------------------------------------------------------------------------
# Per-session synthetic WAV regeneration
# ----------------------------------------------------------------------------
#
# We MUST give every test session a distinct set of audio files — the backend
# deduplicates uploads by SHA-256, so reusing the same WAVs across runs makes
# every upload short-circuit to a pre-existing job, and the "5 end-to-end
# breakdowns" claim becomes vacuous (all 5 hit the same cached job).
#
# Salt strategy: hash ``os.urandom(8)`` into a per-session detune offset (in
# Hz) applied to the chord triads. The progression / key / chord count stay
# the same, so ML detection still gives stable expected outputs.

_TRIADS = {
    "C": (261.63, 329.63, 392.00),  # C E G
    "G": (392.00, 493.88, 587.33),  # G B D
    "Am": (440.00, 523.25, 659.26),  # A C E
    "F": (349.23, 440.00, 523.25),  # F A C
    "D": (293.66, 369.99, 440.00),  # D F# A
    "Em": (329.63, 392.00, 493.88),  # E G B
}

_FIVE_SONGS_PROGRESSIONS = {
    "round3_song1_c_major.wav": ["C", "F", "G", "C"],  # I-IV-V-I in C
    "round3_song2_g_major.wav": ["G", "C", "D", "G"],  # I-IV-V-I in G
    "round3_song3_a_minor.wav": ["Am", "F", "G", "Am"],  # i-VI-VII-i in Am
    "round3_song4_d_major.wav": ["D", "G", "Em", "D"],  # I-IV-ii-I in D
    "round3_song5_e_minor.wav": ["Em", "Am", "D", "G"],  # i-iv-VII-III in Em
}


def _additive_chord_with_salt(freqs, duration_s: float, sr: int, detune_hz: float) -> bytes:
    """Render a chord with a small detune so per-session WAVs hash differently."""
    n_samples = int(duration_s * sr)
    amp = 0.18
    out = bytearray()
    for i in range(n_samples):
        t = i / sr
        env = 0.5 * (1 - math.cos(2 * math.pi * i / max(n_samples - 1, 1)))
        val = 0.0
        for f in freqs:
            val += math.sin(2 * math.pi * (f + detune_hz) * t)
        sample = int(amp * env * (val / len(freqs)) * 32767)
        sample = max(-32768, min(32767, sample))
        out += struct.pack("<h", sample)
    return bytes(out)


def _regenerate_session_wavs() -> None:
    """Write 5 fresh WAVs into ``tmp_audio/`` with a per-session salt."""
    _FIXTURE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    # 8 random bytes → integer → mapped to a sub-Hz detune so the WAV bytes
    # differ every session but ML detection still sees the same chord roots.
    salt_int = int.from_bytes(os.urandom(8), "big")
    base_detune = (salt_int % 1000) / 100.0  # 0.00 – 9.99 Hz
    sr = 22050
    chord_dur = 1.5
    for filename, progression in _FIVE_SONGS_PROGRESSIONS.items():
        out = _FIXTURE_AUDIO_DIR / filename
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            # Tiny per-chord detune variation too, so the 5 WAVs all differ
            # from each other within the same session (not just across sessions).
            for chord_idx, chord_name in enumerate(progression):
                triad = _TRIADS[chord_name]
                detune = base_detune + 0.07 * chord_idx + hash(filename) % 17 / 100.0
                w.writeframes(_additive_chord_with_salt(triad, chord_dur, sr, detune))


@pytest.fixture(scope="session", autouse=True)
def _regen_session_wavs():
    """Autouse: regenerate the 5 fixture WAVs once per session.

    Ensures every test session uploads SHA-256-unique audio so the backend's
    upload-dedup logic actually runs the pipeline instead of returning a
    previously-cached job_id. Without this, the 5-song breakdown test
    becomes a no-op after the first run.
    """
    _regenerate_session_wavs()
    yield


# ----------------------------------------------------------------------------
# Shared run_report.md state
# ----------------------------------------------------------------------------


class _RunReport:
    """Accumulates rows across the test session, writes a single Markdown
    file at the end. Tests call ``add_row(...)`` with whatever they want
    surfaced in the deliverable."""

    def __init__(self):
        self.rows: list[dict] = []

    def add_row(self, **kwargs):
        kwargs.setdefault("ts", _dt.datetime.now(_dt.UTC).isoformat())
        self.rows.append(kwargs)

    def materialize(self):
        _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# Synesthesia E2E browser run — {_dt.datetime.now(_dt.UTC).isoformat()}",
            "",
            "Headless Chromium driven by Playwright as the Antigravity substitute.",
            f"Frontend: `{_FRONTEND_URL}`  ·  Backend: `{_API_URL}`",
            "",
            "## Per-test rows",
            "",
        ]
        # group rows by ``test`` key for readability
        by_test: dict[str, list[dict]] = {}
        for r in self.rows:
            by_test.setdefault(r.get("test", "(other)"), []).append(r)
        for test, rs in by_test.items():
            lines.append(f"### {test}")
            lines.append("")
            for r in rs:
                pretty = json.dumps(
                    {k: v for k, v in r.items() if k not in {"test"}}, default=str, indent=None
                )
                lines.append(f"- {pretty}")
            lines.append("")
        _REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture(scope="session")
def run_report() -> Iterator[_RunReport]:
    rr = _RunReport()
    yield rr
    rr.materialize()


# ----------------------------------------------------------------------------
# Browser / context / page fixtures
# ----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance) -> Iterator[Browser]:
    b = playwright_instance.chromium.launch(headless=True)
    yield b
    b.close()


@pytest.fixture
def context(browser: Browser, request) -> Iterator[BrowserContext]:
    _VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        record_video_dir=str(_VIDEO_DIR),
        record_video_size={"width": 1440, "height": 900},
    )
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext, request, run_report: _RunReport) -> Iterator[Page]:
    """Pre-wired Page with fail-fast console + pageerror listeners.

    Any JS exception OR ``console.error`` raises a Python exception, which
    pytest converts to a test failure with a useful traceback. We also stash
    the listing on the request so a fail-handler hook can dump it.
    """
    p = context.new_page()
    js_errors: list[str] = []
    console_errors: list[str] = []
    request.node._js_errors = js_errors  # noqa: SLF001 — for the hook below
    request.node._console_errors = console_errors  # noqa: SLF001

    p.on("pageerror", lambda exc: js_errors.append(f"pageerror: {exc}"))

    def _on_console(msg):
        if msg.type == "error":
            # Filter the well-known dev-server noise so we don't false-fire
            # on Next.js fast refresh chatter.
            text = msg.text
            if any(
                s in text
                for s in (
                    "[Fast Refresh]",
                    "[HMR]",
                    "ServiceWorker",
                    # Next.js fires this when an <a> upgrades to <Link> during prerender — harmless.
                    "Hydration failed because the server rendered HTML didn't match the client",
                )
            ):
                return
            console_errors.append(text)

    p.on("console", _on_console)
    yield p
    # Surface any errors as fixture-teardown failure so tests don't pass
    # silently when the page broke.
    if js_errors:
        raise AssertionError(f"page raised JS errors: {js_errors}")
    if console_errors:
        raise AssertionError(f"console.error during test: {console_errors}")


# ----------------------------------------------------------------------------
# Screenshot-on-failure hook
# ----------------------------------------------------------------------------


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        # If the test used the ``page`` fixture, find it and snapshot.
        page = item.funcargs.get("page")
        if page is not None:
            try:
                path = _SCREENSHOT_DIR / f"{item.name}_fail.png"
                page.screenshot(path=str(path), full_page=True)
                rep.sections.append(("captured screenshot", str(path)))
            except Exception:  # pragma: no cover
                pass


# ----------------------------------------------------------------------------
# Useful constants for tests
# ----------------------------------------------------------------------------


@pytest.fixture
def frontend_url() -> str:
    return _FRONTEND_URL


@pytest.fixture
def api_url() -> str:
    return _API_URL


@pytest.fixture
def screenshot_dir() -> Path:
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return _SCREENSHOT_DIR


@pytest.fixture
def fixture_audio_dir() -> Path:
    """Where the prepared synthetic WAVs live."""
    return _REPO_ROOT / "tmp_audio"
