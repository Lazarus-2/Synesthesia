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
    """Wrap a pipeline stage and log duration + attrs, emitting to LangSmith."""
    import os
    t0 = time.perf_counter()
    logger.info("stage.start stage=%s %s", stage, attrs)
    
    run_tree = None
    if os.getenv("LANGCHAIN_TRACING_V2") == "true":
        try:
            from langsmith.run_trees import RunTree
            run_tree = RunTree(
                name=stage,
                run_type="chain",
                inputs=attrs
            )
        except ImportError:
            pass
            
    try:
        yield
    except Exception as exc:
        logger.exception("stage.error stage=%s error=%s", stage, exc)
        if run_tree:
            run_tree.end(error=str(exc))
            run_tree.post()
        raise
    finally:
        dt = (time.perf_counter() - t0) * 1000
        logger.info("stage.end stage=%s duration_ms=%.1f", stage, dt)
        if run_tree and not run_tree.error:
            run_tree.end(outputs={"duration_ms": dt, "status": "success"})
            run_tree.post()
