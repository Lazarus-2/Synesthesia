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

    async def setex(self, key: str, ttl: int, value: str):  # noqa: ARG002
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


@pytest.mark.asyncio
async def test_breaker_trips_to_memory_on_outage():
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)

    fake.fail = True  # redis goes down
    # set falls through to memory and still reports success
    assert await cache.set("k:b", "fallback", ttl_seconds=30) is True
    assert cache._breaker_is_open() is True
    # subsequent get does NOT touch redis (breaker open) and reads memory
    fake.ping_calls = 0
    assert await cache.get("k:b") == "fallback"
    assert fake.ping_calls == 0


@pytest.mark.asyncio
async def test_breaker_reopens_after_cooldown_and_reconnects():
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)

    fake.fail = True
    await cache.set("k:r", "v", ttl_seconds=30)  # trips breaker
    assert cache._redis_available() is False

    # Redis recovers; force the cooldown to have elapsed and state to HALF_OPEN
    # (the state machine transitions OPEN→HALF_OPEN once the epoch passes).
    fake.fail = False
    cache._breaker_open_until = time.time() - 0.1
    # _tick_state() will move OPEN→HALF_OPEN on the next _redis_ready() call;
    # we simulate the same by setting it directly for clarity.
    from backend.services.cache import _STATE_HALF_OPEN
    cache._breaker_state = _STATE_HALF_OPEN

    # Next op should probe redis (ping), close the breaker, and persist there.
    assert await cache.set("k:r2", "v2", ttl_seconds=30) is True
    assert fake.store["k:r2"] == "v2"
    assert cache._breaker_is_open() is False


@pytest.mark.asyncio
async def test_ping_stays_false_while_breaker_open():
    from backend.services.cache import _STATE_OPEN
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)
    cache._breaker_state = _STATE_OPEN
    cache._breaker_open_until = time.time() + 100  # forced open
    assert await cache.ping() is False
    # No real ping attempted while open.
    assert fake.ping_calls == 0


# ---------------------------------------------------------------------------
# Fix 2+3: half-open single-probe under lock (thundering-herd prevention)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_half_open_only_one_probe_on_concurrent_gets():
    """When N coroutines hit _redis_ready() simultaneously in HALF_OPEN state,
    exactly one probe (ping) should fire; the rest should use memory for that call.

    This verifies the thundering-herd prevention: in a single asyncio event loop
    the coroutines yield at ``await`` points.  The first coroutine to run
    acquires the lock and probes; all other coroutines see the lock busy and
    fall back to memory immediately.  After the probe the breaker is closed.

    The key is seeded in both stores so every caller (probe-holder and
    memory-fallback callers alike) gets a non-None result.
    """
    from backend.services.cache import _STATE_HALF_OPEN
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)

    # Seed the key in both stores so all callers return a value.
    fake.store["k:ho"] = "redis-val"
    cache.memory_store["k:ho"] = ("mem-val", None)

    # Put the breaker directly into HALF_OPEN with an expired cooldown.
    cache._breaker_open_until = time.time() - 0.1
    cache._breaker_state = _STATE_HALF_OPEN

    # Fire 8 concurrent gets.
    results = await asyncio.gather(*[cache.get("k:ho") for _ in range(8)])

    # Redis ping should have been called exactly once (the single probe).
    assert fake.ping_calls == 1, f"expected 1 probe, got {fake.ping_calls}"

    # Breaker should be closed after a successful probe.
    assert not cache._breaker_is_open()

    # All callers must get a non-None value: probe-holder reads "redis-val"
    # from Redis; concurrent non-probe callers read "mem-val" from memory.
    assert all(r is not None for r in results), f"got Nones: {results}"


@pytest.mark.asyncio
async def test_half_open_re_trips_on_failed_probe():
    """If the single probe fails, the breaker re-trips (cooldown resets)."""
    from backend.services.cache import _STATE_HALF_OPEN
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)

    # Trip the breaker.
    fake.fail = True
    await cache.set("k:retrp", "v", ttl_seconds=30)
    # Cooldown elapsed but redis is still broken (raise_on_ping only).
    fake.fail = False
    fake.raise_on_ping = True
    cache._breaker_open_until = time.time() - 0.1
    cache._breaker_state = _STATE_HALF_OPEN  # advance to HALF_OPEN

    result = await cache.get("k:retrp")
    # Probe fired and failed → breaker re-tripped to OPEN.
    assert fake.ping_calls == 1
    assert cache._breaker_is_open()
    # Value must still come back from memory.
    assert result == "v"


# ---------------------------------------------------------------------------
# Fix 4: memory-shadow consistency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_mirrors_value_to_memory_store():
    """Successful Redis write must also update memory_store so a later
    outage doesn't serve a stale (pre-write) shadow value.
    """
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)

    # Seed a stale shadow so we can confirm it gets overwritten.
    cache.memory_store["k:shadow"] = ("old-val", None)

    await cache.set("k:shadow", "new-val", ttl_seconds=60)

    # Redis got the new value.
    assert fake.store["k:shadow"] == "new-val"
    # Memory shadow was updated too.
    assert cache.memory_store["k:shadow"][0] == "new-val"


@pytest.mark.asyncio
async def test_delete_removes_from_memory_store_unconditionally():
    """delete() must evict from memory_store regardless of Redis availability."""
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)

    # Write through both stores.
    await cache.set("k:del", "bye", ttl_seconds=30)
    assert "k:del" in cache.memory_store

    # Delete succeeds.
    assert await cache.delete("k:del") is True

    # Evicted from both.
    assert "k:del" not in cache.memory_store
    assert "k:del" not in fake.store


@pytest.mark.asyncio
async def test_delete_removes_memory_even_when_breaker_open():
    """delete() must still remove the memory-store entry when Redis is down."""
    from backend.services.cache import _STATE_OPEN
    fake = FakeAsyncRedis()
    cache = HybridCache()
    _attach_fake(cache, fake)

    cache.memory_store["k:brkdel"] = ("stranded", None)
    # Force the breaker open so the Redis path is skipped.
    cache._breaker_state = _STATE_OPEN
    cache._breaker_open_until = time.time() + 100

    assert await cache.delete("k:brkdel") is True
    assert "k:brkdel" not in cache.memory_store
