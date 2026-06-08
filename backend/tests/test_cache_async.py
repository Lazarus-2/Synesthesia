"""Async HybridCache tests (Group 4 — redis.asyncio migration + FT-03).

No fakeredis dependency: a minimal in-process async fake redis lives here.
It implements just the subset HybridCache touches (get/set/setex/delete/ping)
and can be told to start raising to simulate an outage.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.services.cache import HybridCache


class FakeAsyncRedis:
    """Async stand-in for redis.asyncio.Redis used by HybridCache.

    ``fail`` flips every call to raise ConnectionError, modelling an outage.
    ``raise_on_ping`` is independent so a breaker can recover on a later ping.
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.fail = False
        self.raise_on_ping = False
        self.ping_calls = 0

    def _maybe_fail(self) -> None:
        if self.fail:
            raise ConnectionError("simulated redis outage")

    async def get(self, key: str):
        self._maybe_fail()
        return self.store.get(key)

    async def set(self, key: str, value: str):
        self._maybe_fail()
        self.store[key] = value
        return True

    async def setex(self, key: str, ttl: int, value: str):
        self._maybe_fail()
        self.store[key] = value
        return True

    async def delete(self, key: str):
        self._maybe_fail()
        self.store.pop(key, None)
        return 1

    async def ping(self):
        self.ping_calls += 1
        if self.raise_on_ping or self.fail:
            raise ConnectionError("ping failed")
        return True


def _attach_fake(cache: HybridCache, fake: FakeAsyncRedis) -> None:
    """Wire a fake client into a cache built with no real connection."""
    cache.redis_client = fake


@pytest.mark.asyncio
async def test_set_get_round_trip_through_redis():
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)

    assert await cache.set("k:roundtrip", "value-1", ttl_seconds=30) is True
    assert await cache.get("k:roundtrip") == "value-1"
    # It really went through the fake redis, not the memory store.
    assert fake.store["k:roundtrip"] == "value-1"


@pytest.mark.asyncio
async def test_get_missing_key_returns_none():
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)
    assert await cache.get("k:absent") is None


@pytest.mark.asyncio
async def test_memory_fallback_when_no_client():
    cache = HybridCache()
    cache.redis_client = None  # never connected
    assert await cache.set("k:mem", "m", ttl_seconds=5) is True
    assert await cache.get("k:mem") == "m"


@pytest.mark.asyncio
async def test_memory_fallback_ttl_expiry():
    cache = HybridCache()
    cache.redis_client = None
    cache.memory_store["k:exp"] = ("stale", time.time() - 1)
    assert await cache.get("k:exp") is None


@pytest.mark.asyncio
async def test_ping_true_when_client_healthy():
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)
    assert await cache.ping() is True


@pytest.mark.asyncio
async def test_ping_false_when_no_client():
    cache = HybridCache()
    cache.redis_client = None
    assert await cache.ping() is False
