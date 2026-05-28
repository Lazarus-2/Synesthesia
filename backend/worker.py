import os
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

result_backend = RedisAsyncResultBackend(redis_url=redis_url)

# Using ListQueueBroker for Taskiq which leverages Redis
broker = ListQueueBroker(
    url=redis_url,
).with_result_backend(result_backend)
