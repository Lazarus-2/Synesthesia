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


class HybridCache:
    """Async hybrid cache over redis.asyncio with an in-memory TTL fallback.

    Redis failures trip a circuit breaker (``_breaker_open_until``) instead of
    permanently nulling the client: after a cooldown a single operation is
    allowed to re-establish the connection.
    """

    def __init__(self) -> None:
        self.redis_client = None
        self.memory_store: dict[str, tuple[str, float | None]] = {}
        # Epoch after which a reconnect attempt is permitted. 0 == closed.
        self._breaker_open_until: float = 0.0
        self._lock = asyncio.Lock()

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
        return time.time() < self._breaker_open_until

    def _trip_breaker(self, err: Exception) -> None:
        """Open the breaker for the cooldown window and log it."""
        self._breaker_open_until = time.time() + _BREAKER_COOLDOWN_S
        logger.warning(
            "HybridCache: redis op failed (%s); breaker open for %.0fs.",
            err,
            _BREAKER_COOLDOWN_S,
        )

    def _redis_available(self) -> bool:
        """Whether we should attempt a real redis op right now."""
        if self.redis_client is None:
            return False
        if self._breaker_is_open():
            return False
        return True

    async def get(self, key: str) -> str | None:
        """Fetch a stringified item; fall back to memory on outage."""
        if self._redis_available():
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
        if self._redis_available():
            try:
                if ttl_seconds:
                    await self.redis_client.setex(key, ttl_seconds, value)
                else:
                    await self.redis_client.set(key, value)
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
        if self._redis_available():
            try:
                await self.redis_client.delete(key)
                return True
            except Exception as err:
                self._trip_breaker(err)

        if key in self.memory_store:
            del self.memory_store[key]
            return True
        return False

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
