"""Structured JSON logging — no extra runtime dep.

Drop-in formatter that turns every ``logger.info("msg", extra={...})`` (or
``logger.warning("template %s", arg)``) into a single-line JSON record:

    {"ts": "...", "level": "INFO", "logger": "backend.main",
     "msg": "...", "module": "main", "line": 42, ...}

Why hand-rolled and not structlog?
----------------------------------
This codebase has enough deps already. The stdlib ``logging`` module plus a
custom ``Formatter`` produces something that any modern log aggregator
(Datadog, CloudWatch, Grafana Loki) can parse natively, in ~40 lines, with
zero new pip installs.

Usage
-----
Call :func:`configure_logging` exactly once at process start — currently
from the FastAPI ``lifespan`` and the Taskiq worker (so both API and worker
agree on the format).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime

# Reserved attribute names that ``logging.LogRecord`` carries unconditionally —
# we don't want to clutter every output line with them, but we *do* want any
# custom ``extra={...}`` fields the caller passed.
_RECORD_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
    }
)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        # Surface any caller-supplied ``extra={...}`` fields.
        for k, v in record.__dict__.items():
            if k in _RECORD_RESERVED or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                out[k] = v
            except (TypeError, ValueError):
                out[k] = repr(v)
        return json.dumps(out, separators=(",", ":"), ensure_ascii=False)


def configure_logging(level: str | None = None) -> None:
    """Install the JSON formatter on the root logger.

    The format is structured only when ``LOG_FORMAT=json`` (the default in
    containerized envs). Set ``LOG_FORMAT=plain`` for local development if
    JSON lines are hard to read in a terminal.
    """
    root = logging.getLogger()
    # Idempotent: if we've already attached a JSONFormatter, no-op.
    if any(
        isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JSONFormatter)
        for h in root.handlers
    ):
        return

    use_json = os.getenv("LOG_FORMAT", "json").lower() == "json"
    handler = logging.StreamHandler(sys.stdout)
    if use_json:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s — %(message)s")
        )
    # Reset existing handlers so duplicate output doesn't sneak in across reloads.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    resolved_level = level or os.getenv("LOG_LEVEL") or "INFO"
    root.setLevel(resolved_level.upper())
