import time

from backend.config import get_settings

settings = get_settings()

class HybridCache:
    """Dynamic caching engine providing safe Redis pipelines and memory backup routes."""
    def __init__(self):
        self.redis_client = None
        self.memory_store = {}  # Structure: {key: (value_str, expire_epoch)}
        
        if settings.redis_url:
            try:
                import redis
                # Establish standard client pool connection
                self.redis_client = redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_timeout=2.0
                )
                self.redis_client.ping()
                print("HybridCache: Redis initialized successfully as active engine.")
            except Exception as e:
                print(f"HybridCache: Redis connection offline ({e}). Fallback to local TTL active.")
                self.redis_client = None

    def get(self, key: str) -> str | None:
        """Fetch stringified item from the active store."""
        if self.redis_client:
            try:
                return self.redis_client.get(key)
            except Exception as err:
                print(f"HybridCache: Redis GET pipeline failure ({err}), failing over...")
                self.redis_client = None
                
        # Resolve from memory cache
        if key in self.memory_store:
            val, expires = self.memory_store[key]
            if expires is None or expires > time.time():
                return val
            # Auto-purge expired key
            del self.memory_store[key]
        return None

    def set(self, key: str, value: str, ttl_seconds: int | None = 1800) -> bool:
        """Persist stringified item with expiration (default 30 mins)."""
        if self.redis_client:
            try:
                if ttl_seconds:
                    self.redis_client.setex(key, ttl_seconds, value)
                else:
                    self.redis_client.set(key, value)
                return True
            except Exception as err:
                print(f"HybridCache: Redis SET pipeline failure ({err}), failing over...")
                self.redis_client = None
                
        # Write to memory backup
        expires = time.time() + ttl_seconds if ttl_seconds else None
        self.memory_store[key] = (value, expires)
        return True

    def delete(self, key: str) -> bool:
        """Evict item from cache repositories."""
        if self.redis_client:
            try:
                self.redis_client.delete(key)
                return True
            except Exception as err:
                print(f"HybridCache: Redis DEL pipeline failure ({err}), failing over...")
                self.redis_client = None
                
        if key in self.memory_store:
            del self.memory_store[key]
            return True
        return False

# Export unified singleton container
cache = HybridCache()
