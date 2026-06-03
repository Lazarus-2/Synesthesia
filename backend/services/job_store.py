"""Unified job state interface (Plan 2 A2).

Before this module, progress lived in Redis (fast, ephemeral) and the
final result lived in MongoDB (durable, queryable). Endpoints knew about
both stores directly, the SSE timeout was hardcoded, and worker
heartbeats were ad-hoc.

This module collapses that into a single :class:`JobStore` interface so
endpoints and the analysis task talk to *one* thing for the lifecycle of a
job. The default implementation (:class:`HybridJobStore`) routes
in-progress state to Redis and persistence to Mongo internally, so we
keep the original locality benefits without forcing endpoints to know
about the split.

Lifecycle
---------
    set_progress() ──repeatedly─→ get_progress() (SSE polls)
                                       │
                                       ▼
    heartbeat() ─periodically─→ is_stale() ── True ──→ progress="error"
                                       │
                                       ▼
                                finalize() ──→ get_result() (cache hits)

The ``JobStore`` is process-shared, not per-request — get the singleton
via :func:`get_job_store`.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Protocol, runtime_checkable

from backend.services.cache import cache

logger = logging.getLogger(__name__)


# Default heartbeat staleness window. If a job's last heartbeat is older
# than this, ``is_stale()`` reports True so the SSE handler can surface
# "worker likely crashed" instead of waiting indefinitely.
DEFAULT_HEARTBEAT_TIMEOUT_S = 60

# How long progress entries live in Redis before automatic eviction. Longer
# than any plausible analysis so a slow LLM doesn't lose its progress.
DEFAULT_PROGRESS_TTL_S = 24 * 60 * 60


def _progress_key(job_id: str) -> str:
    return f"song:analysis:{job_id}"


def _heartbeat_key(job_id: str) -> str:
    return f"song:analysis:{job_id}:hb"


@runtime_checkable
class JobStore(Protocol):
    """Storage interface for job lifecycle state."""

    def set_progress(self, job_id: str, payload: dict) -> None: ...
    def get_progress(self, job_id: str) -> dict | None: ...
    def heartbeat(self, job_id: str) -> None: ...
    def is_stale(self, job_id: str, *, timeout_s: int = DEFAULT_HEARTBEAT_TIMEOUT_S) -> bool: ...
    def cache_response(self, job_id: str, response_json: str) -> None: ...
    def get_cached_response(self, job_id: str) -> str | None: ...


class HybridJobStore:
    """Redis-backed progress + heartbeats; result responses live behind the
    same cache layer (which also fronts MongoDB on cache miss in the
    endpoint).

    Why not stuff the durable result here too?
    ------------------------------------------
    Final analysis records live in Mongo via :class:`SongAnalysisModel` —
    that storage is queryable, indexed (Plan 2 E1), and TTL'd. Layering a
    second persistence path through this interface would obscure that
    canonical location and double the surface area. The endpoint pattern
    is: read progress from job_store; read final from Mongo via the
    existing ``song_analyses`` collection; cache the latter via
    :meth:`cache_response` for fast subsequent GETs.
    """

    def set_progress(self, job_id: str, payload: dict) -> None:
        cache.set(_progress_key(job_id), json.dumps(payload), ttl_seconds=DEFAULT_PROGRESS_TTL_S)
        # Every progress write is itself a heartbeat — the worker is alive.
        self.heartbeat(job_id)

    def get_progress(self, job_id: str) -> dict | None:
        raw = cache.get(_progress_key(job_id))
        if not raw:
            return None
        try:
            decoded: dict = json.loads(raw)
            return decoded
        except json.JSONDecodeError:
            logger.warning("malformed progress payload for job %s", job_id)
            return None

    def heartbeat(self, job_id: str) -> None:
        cache.set(_heartbeat_key(job_id), str(time.time()), ttl_seconds=DEFAULT_PROGRESS_TTL_S)

    def is_stale(self, job_id: str, *, timeout_s: int = DEFAULT_HEARTBEAT_TIMEOUT_S) -> bool:
        raw = cache.get(_heartbeat_key(job_id))
        if not raw:
            # No heartbeat yet → not stale, just not started. The endpoint's
            # own SSE timeout handles "worker never ran."
            return False
        try:
            last = float(raw)
        except ValueError:
            return False
        return (time.time() - last) > timeout_s

    def cache_response(self, job_id: str, response_json: str) -> None:
        cache.set(_progress_key(job_id), response_json, ttl_seconds=DEFAULT_PROGRESS_TTL_S)

    def get_cached_response(self, job_id: str) -> str | None:
        return cache.get(_progress_key(job_id))


# Process-singleton — endpoints and the worker task both fetch via this.
_singleton: JobStore = HybridJobStore()


def get_job_store() -> JobStore:
    return _singleton


def set_job_store_for_tests(store: JobStore) -> None:
    """Override the singleton from a test fixture. No-op in production code."""
    global _singleton
    _singleton = store
