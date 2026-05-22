"""
Tracing + structured logging.
Vault ref: 02-LLM-Architecture/05-Observability-Reliability.md
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from backend.config import get_settings

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("soundbreak")


@contextmanager
def trace(stage: str, **attrs):
    """Wrap a pipeline stage and log duration + attrs.
    TODO(Module 2, Lesson 5): emit to LangSmith / OpenTelemetry.
    """
    t0 = time.perf_counter()
    logger.info("stage.start stage=%s %s", stage, attrs)
    try:
        yield
    except Exception as exc:
        logger.exception("stage.error stage=%s error=%s", stage, exc)
        raise
    finally:
        dt = (time.perf_counter() - t0) * 1000
        logger.info("stage.end stage=%s duration_ms=%.1f", stage, dt)
