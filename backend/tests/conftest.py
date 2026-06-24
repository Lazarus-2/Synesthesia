"""Shared pytest fixtures (Plan 3 D1).

The synthetic_song fixture replaces the missing ``tests/audio/test_song.mp3``
that historically caused pipeline tests to skip silently. It generates a
deterministic short WAV from a known chord progression so:

  * Pipeline integration tests can always run (no licensing concerns).
  * Expected values (key, tempo, chord) are knowable up front.
  * Tests stay hermetic — no network, no LLM, no Mongo.

Heavier-weight fixtures (mock Mongo, mock JobStore, dependency overrides)
live here too so each test file doesn't re-implement them.
"""

from __future__ import annotations

import math
import struct
import wave
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ``backend`` is importable via the editable install (pip install -e .) — no
# sys.path shim needed.


# ---------------------------------------------------------------------------
# Synthetic audio
# ---------------------------------------------------------------------------

_C_MAJOR_TRIAD_HZ = (261.63, 329.63, 392.00)  # C4, E4, G4
_G_MAJOR_TRIAD_HZ = (392.00, 493.88, 587.33)  # G4, B4, D5
_A_MINOR_TRIAD_HZ = (440.00, 523.25, 659.26)  # A4, C5, E5
_F_MAJOR_TRIAD_HZ = (349.23, 440.00, 523.25)  # F4, A4, C5

_C_MAJOR_PROGRESSION = [
    _C_MAJOR_TRIAD_HZ,
    _G_MAJOR_TRIAD_HZ,
    _A_MINOR_TRIAD_HZ,
    _F_MAJOR_TRIAD_HZ,
]


def _additive_chord(freqs: tuple[float, ...], duration_s: float, sr: int) -> bytes:
    """Render a chord as 16-bit PCM mono. Soft envelope to avoid clicks."""
    n_samples = int(duration_s * sr)
    amp = 0.18  # leave headroom for librosa
    samples = bytearray()
    for i in range(n_samples):
        t = i / sr
        # Hann envelope so chord boundaries don't pop.
        env = 0.5 * (1 - math.cos(2 * math.pi * i / max(n_samples - 1, 1)))
        val = 0.0
        for f in freqs:
            val += math.sin(2 * math.pi * f * t)
        sample = int(amp * env * (val / len(freqs)) * 32767)
        sample = max(-32768, min(32767, sample))
        samples += struct.pack("<h", sample)
    return bytes(samples)


def _write_synthetic_wav(
    path: Path,
    progression: list[tuple[float, ...]] = _C_MAJOR_PROGRESSION,
    chord_duration_s: float = 1.5,
    sample_rate: int = 22050,
) -> None:
    """Render the progression to a 16-bit mono WAV file at ``path``."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for triad in progression:
            w.writeframes(_additive_chord(triad, chord_duration_s, sample_rate))


def make_click_track_wav(
    path: Path,
    *,
    bpm: int = 120,
    numerator: int = 4,
    n_measures: int = 8,
    sample_rate: int = 22050,
) -> Path:
    """Render a metronome click track with accented downbeats (Phase 5 G1).

    Every beat is a short percussive click; the first beat of each measure
    (``i % numerator == 0``) is louder and carries a low-frequency thump, so
    the onset envelope has a clear accent periodicity of ``numerator``. Used
    to exercise the deterministic meter detector on real librosa features.
    """
    spb = 60.0 / bpm
    total_beats = n_measures * numerator
    n_total = int(total_beats * spb * sample_rate)
    buf = bytearray()
    click_dur = 0.05
    click_n = int(click_dur * sample_rate)

    samples = [0.0] * n_total
    for b in range(total_beats):
        start = int(b * spb * sample_rate)
        downbeat = (b % numerator) == 0
        amp = 0.6 if downbeat else 0.28
        for j in range(click_n):
            idx = start + j
            if idx >= n_total:
                break
            env = math.exp(-8.0 * j / click_n)  # fast percussive decay
            t = j / sample_rate
            val = math.sin(2 * math.pi * 1000.0 * t)
            if downbeat:
                val += math.sin(2 * math.pi * 80.0 * t)  # kick thump on the 1
                val *= 0.5
            samples[idx] += amp * env * val

    for s in samples:
        clamped = max(-1.0, min(1.0, s))
        buf += struct.pack("<h", int(clamped * 32767))

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(bytes(buf))
    return path


@pytest.fixture(scope="session")
def synthetic_song(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a Path to a deterministic 6-second test WAV.

    Session-scoped so the file is rendered once across the whole test run.
    Known properties:
      - Key: ~C major
      - Tempo: arbitrary (it's chord blocks, not beats)
      - Sample rate: 22050
      - Duration: 6.0 seconds (4 chords × 1.5s)
    """
    out = tmp_path_factory.mktemp("synthetic_audio") / "test_song.wav"
    _write_synthetic_wav(out)
    return out


# ---------------------------------------------------------------------------
# DB / auth helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mongo() -> MagicMock:
    """In-memory async-Mongo stub.

    Each collection has ``find_one``, ``find``, ``insert_one``, ``update_one``,
    ``replace_one``, ``count_documents`` as AsyncMocks. Tests can override the
    return value per call: ``mock_mongo.users.find_one.return_value = {...}``.
    """
    db = MagicMock()
    for coll in ("users", "chat_sessions", "song_analyses", "failed_jobs", "collections"):
        c = getattr(db, coll)
        c.find_one = AsyncMock(return_value=None)
        c.insert_one = AsyncMock()
        c.update_one = AsyncMock()
        c.replace_one = AsyncMock()
        c.delete_one = AsyncMock()
        c.count_documents = AsyncMock(return_value=0)
        # ``find`` returns a chain object (find().sort().skip().limit()) that
        # is itself async-iterable. We model it as an AsyncMock returning
        # another MagicMock whose chain methods are self-returning.
        chain = MagicMock()
        chain.sort.return_value = chain
        chain.skip.return_value = chain
        chain.limit.return_value = chain

        async def _aiter():
            return
            yield  # never reached, makes this an async generator

        chain.__aiter__ = lambda self=chain: _aiter()
        c.find = MagicMock(return_value=chain)
    return db


@pytest.fixture
def api_client(mock_mongo):
    """FastAPI TestClient with get_mongodb overridden to ``mock_mongo``.

    Sets a placeholder ``_db`` sentinel so importing main.py doesn't trigger
    the "MongoDB not initialized" guard. Yields a context-manager-style
    client; teardown clears dependency overrides.
    """
    import logging

    logging.getLogger().setLevel(logging.CRITICAL)
    import backend.database as _dbmod

    _dbmod._db = object()

    from fastapi.testclient import TestClient

    from backend.database import get_mongodb
    from backend.main import app

    app.dependency_overrides[get_mongodb] = lambda: mock_mongo
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_mongodb, None)


@pytest.fixture(autouse=True)
def _quiet_logs(caplog) -> Iterator[None]:
    """Stop the JSON formatter from spamming test output with cache-init lines."""
    import logging

    logging.getLogger("backend").setLevel(logging.WARNING)
    yield
