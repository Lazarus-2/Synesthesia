"""Taskiq broker for background analysis jobs.

Middlewares
-----------
- :class:`SimpleRetryMiddleware` re-enqueues failed tasks (opt-in per task
  via the ``retry_on_error`` label; max attempts per task via ``max_retries``).

Lifecycle
---------
- ``WORKER_STARTUP`` (commented out for now): would be the place to eagerly
  warm the LangGraph compile cost. Skipped because the lazy ``get_graph()``
  inside the task already pays the cost on the first invocation and the
  difference is tens of ms, not seconds.
- ``WORKER_SHUTDOWN`` logs a clear "shutting down" line so operators can see
  it in container logs. Full in-flight job tracking (mark interrupted on
  SIGTERM) is deferred — would need an "active jobs" registry tied to task
  middleware. Defended at the deploy layer via docker-compose
  ``stop_grace_period`` so Taskiq can finish active jobs cleanly.
"""
from __future__ import annotations

import logging
import os

from taskiq import SimpleRetryMiddleware, TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

logger = logging.getLogger(__name__)

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

result_backend = RedisAsyncResultBackend(redis_url=redis_url)

broker = (
    ListQueueBroker(url=redis_url)
    .with_result_backend(result_backend)
    .with_middlewares(
        # default_retry_count=3 means a task that opts in with
        # ``retry_on_error=True`` will be re-tried up to 3 times by default;
        # individual tasks can override via the ``max_retries`` label.
        SimpleRetryMiddleware(default_retry_count=3),
    )
)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _on_worker_startup(state: TaskiqState) -> None:
    from backend.observability.logging_config import configure_logging
    from backend.observability.tracing import configure_tracing
    configure_logging()
    configure_tracing(service_name="synesthesia-worker")
    logger.info("Taskiq worker started")


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _on_worker_shutdown(state: TaskiqState) -> None:
    logger.info("Taskiq worker shutdown event received; finishing in-flight jobs")
