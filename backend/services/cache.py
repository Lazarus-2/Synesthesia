import asyncio
import logging
import time

from backend.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# How long the breaker stays open before the next operation is allowed to
# retry the real Redis connection. Short enough that a flapping Redis
# recovers quickly; long enough that we don't hammer a dead socket per call.
_BREAKER_COOLDOWN_S = 5.0

# Breaker states
_STATE_CLOSED = "closed"      # normal; pass through to Redis
_STATE_OPEN = "open"          # cooling down; use memory only
_STATE_HALF_OPEN = "half_open"  # cooldown elapsed; exactly one probe allowed


class HybridCache:
    """Async hybrid cache over redis.asyncio with an in-memory TTL fallback.

    Redis failures trip a circuit breaker instead of permanently nulling the
    client.  The breaker moves through three states:

    * CLOSED  — pass all ops through to Redis.
    * OPEN    — cooldown window; all ops use in-memory fallback.
    * HALF_OPEN — cooldown elapsed; exactly ONE coroutine probes Redis (ping)
                  under ``_lock``.  Other concurrent callers that cannot
                  immediately acquire the lock use memory for that one call
                  rather than all racing to probe (thundering-herd prevention).
                  On probe success → CLOSED; on failure → OPEN (reset cooldown).
    """

    def __init__(self) -> None:
        self.redis_client = None
        self.memory_store: dict[str, tuple[str, float | None]] = {}
        # Epoch after which the HALF_OPEN transition fires. 0 == CLOSED.
        self._breaker_open_until: float = 0.0
        self._breaker_state: str = _STATE_CLOSED
        self._lock = asyncio.Lock()
        # Guards the read-modify-write of the in-memory counter fallback in incr().
        self._incr_lock = asyncio.Lock()

        if settings.redis_url:
            self._connect()

    def _connect(self) -> None:
        """(Re)build the async client. Lazy ping happens on first real op."""
        try:
            import redis.asyncio as aioredis

            self.redis_client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            logger.info("HybridCache: redis.asyncio client constructed.")
        except Exception as exc:  # pragma: no cover - import/url errors only
            logger.warning("HybridCache: could not construct redis client: %s", exc)
            self.redis_client = None

    def _breaker_is_open(self) -> bool:
        """True while we are in the cooldown window after a failure."""
        return self._breaker_state == _STATE_OPEN and time.time() < self._breaker_open_until

    def _trip_breaker(self, err: Exception) -> None:
        """Open the breaker for the cooldown window and log it."""
        self._breaker_open_until = time.time() + _BREAKER_COOLDOWN_S
        self._breaker_state = _STATE_OPEN
        logger.warning(
            "HybridCache: redis op failed (%s); breaker open for %.0fs.",
            err,
            _BREAKER_COOLDOWN_S,
        )

    def _redis_available(self) -> bool:
        """Whether we should attempt a real redis op right now (no lock check).

        Returns True only when state is CLOSED.  OPEN and HALF_OPEN both
        return False so callers default to memory.  Used by ``ping()`` (which
        has its own simpler contract) and kept for backwards-compatibility.
        """
        if self.redis_client is None:
            return False
        return self._breaker_state == _STATE_CLOSED

    def _tick_state(self) -> None:
        """Advance OPEN → HALF_OPEN once the cooldown has elapsed.

        Call this before any readiness check so the state machine stays
        consistent without requiring callers to understand time math.
        """
        if (
            self._breaker_state == _STATE_OPEN
            and time.time() >= self._breaker_open_until
        ):
            self._breaker_state = _STATE_HALF_OPEN

    async def _redis_ready(self) -> bool:
        """Evaluate readiness including a half-open probe after cooldown.

        State transitions:
        - CLOSED  → return True immediately (fast path).
        - OPEN within cooldown → return False (use memory).
        - OPEN, cooldown elapsed → transition to HALF_OPEN.
        - HALF_OPEN, lock free → one coroutine enters, probes via ping:
            - probe OK  → transition to CLOSED, return True.
            - probe fail → re-trip (back to OPEN), return False.
        - HALF_OPEN, lock busy (another probe in progress) → return False
          (the concurrent caller uses memory for this call only).
        """
        if self.redis_client is None:
            return False

        # Advance OPEN → HALF_OPEN if the cooldown elapsed.
        self._tick_state()

        if self._breaker_state == _STATE_CLOSED:
            return True

        if self._breaker_state == _STATE_OPEN:
            # Still within the cooldown window.
            return False

        # HALF_OPEN: allow exactly one probe under the lock.
        if self._lock.locked():
            # Another coroutine is already probing; use memory for this call.
            return False

        async with self._lock:
            # Re-check state inside the lock: a concurrent probe may have
            # already closed or re-tripped the breaker.
            self._tick_state()
            if self._breaker_state == _STATE_CLOSED:
                return True
            if self._breaker_state == _STATE_OPEN:
                return False

            # Still HALF_OPEN — we are the probe coroutine.
            try:
                await self.redis_client.ping()
                # Probe succeeded → close the breaker.
                self._breaker_state = _STATE_CLOSED
                self._breaker_open_until = 0.0
                logger.info("HybridCache: breaker closed after successful probe.")
                return True
            except Exception as err:
                self._trip_breaker(err)
                return False

    async def get(self, key: str) -> str | None:
        """Fetch a stringified item; fall back to memory on outage."""
        if await self._redis_ready():
            try:
                return await self.redis_client.get(key)
            except Exception as err:
                self._trip_breaker(err)

        if key in self.memory_store:
            val, expires = self.memory_store[key]
            if expires is None or expires > time.time():
                return val
            del self.memory_store[key]
        return None

    async def set(self, key: str, value: str, ttl_seconds: int | None = 1800) -> bool:
        """Persist a stringified item with expiration (default 30 mins)."""
        if await self._redis_ready():
            try:
                if ttl_seconds:
                    await self.redis_client.setex(key, ttl_seconds, value)
                else:
                    await self.redis_client.set(key, value)
                # Fix 4: mirror successful Redis write into the memory shadow
                # so a later outage doesn't serve a stale first-outage value.
                expires = time.time() + ttl_seconds if ttl_seconds else None
                self.memory_store[key] = (value, expires)
                return True
            except Exception as err:
                self._trip_breaker(err)

        expires = time.time() + ttl_seconds if ttl_seconds else None
        self.memory_store[key] = (value, expires)
        return True

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Explicit setex alias for callers that want the redis-native verb."""
        return await self.set(key, value, ttl_seconds=ttl_seconds)

    async def delete(self, key: str) -> bool:
        """Evict an item from both stores."""
        # Fix 4: always remove from memory regardless of Redis path.
        self.memory_store.pop(key, None)
        if await self._redis_ready():
            try:
                await self.redis_client.delete(key)
                return True
            except Exception as err:
                self._trip_breaker(err)
                return True  # evicted from memory; best-effort on Redis

        return True

    async def incr(self, key: str, delta: int = 1, ttl_seconds: int | None = None) -> int | None:
        """Atomically add ``delta`` to an integer counter and return the new total.

        Uses Redis INCRBY (atomic across processes/coroutines) + EXPIRE; on a
        Redis outage falls back to a lock-guarded in-process counter. Returns
        ``None`` only on a hard cache error so callers can fail-open.
        """
        if await self._redis_ready():
            try:
                new_total = await self.redis_client.incrby(key, delta)
                if ttl_seconds:
                    await self.redis_client.expire(key, ttl_seconds)
                expires = time.time() + ttl_seconds if ttl_seconds else None
                self.memory_store[key] = (str(new_total), expires)
                return int(new_total)
            except Exception as err:
                self._trip_breaker(err)

        # Memory fallback — lock the RMW so concurrent coroutines don't race.
        async with self._incr_lock:
            cur = 0
            if key in self.memory_store:
                val, expires = self.memory_store[key]
                if expires is None or expires > time.time():
                    try:
                        cur = int(val)
                    except (TypeError, ValueError):
                        cur = 0
            new_total = cur + delta
            expires = time.time() + ttl_seconds if ttl_seconds else None
            self.memory_store[key] = (str(new_total), expires)
            return new_total

    async def ping(self) -> bool:
        """Liveness probe. Reconnects through the breaker if cooldown elapsed."""
        if self.redis_client is None:
            return False
        if self._breaker_is_open():
            return False
        try:
            await self.redis_client.ping()
            return True
        except Exception as err:
            self._trip_breaker(err)
            return False


# Export unified singleton container
cache = HybridCache()
