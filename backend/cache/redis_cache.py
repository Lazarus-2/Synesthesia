"""
Redis-backed cache for expensive analyses.
Key = hash(audio file content). Hit -> skip feature extraction entirely.
Vault ref: 05-Production-Systems/02-Latency-Cost-Quality.md
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.config import get_settings


def audio_fingerprint(audio_path: str | Path) -> str:
    """Fast content-based hash. TODO(Module 5, Lesson 2): use chunked sha1."""
    h = hashlib.sha1()
    with open(audio_path, "rb") as f:
        # Sample start + middle + end to keep it fast on large files
        h.update(f.read(1024 * 1024))
    return h.hexdigest()


def cache_get(key: str) -> dict | None:
    """TODO(Module 5): open real Redis connection."""
    # import redis
    # r = redis.from_url(get_settings().redis_url)
    # raw = r.get(f"sb:{key}")
    # return json.loads(raw) if raw else None
    return None


def cache_set(key: str, value: dict, ttl_seconds: int = 60 * 60 * 24 * 7) -> None:
    """TODO(Module 5): open real Redis connection."""
    # import redis
    # r = redis.from_url(get_settings().redis_url)
    # r.setex(f"sb:{key}", ttl_seconds, json.dumps(value))
    return None
