"""Optional Sentry error tracking (opt-in).

Mirrors the graceful-when-unset pattern used for LangSmith/OTel: when
``SENTRY_DSN`` is empty (the default), :func:`init_sentry` is a no-op and
``sentry_sdk`` is never imported, keeping local/dev/test runs clean and
dependency-light. Set ``SENTRY_DSN`` per-deploy to turn it on.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_sentry() -> bool:
    """Initialize Sentry iff SENTRY_DSN is configured. Returns True if initialized.

    No-op (returns False) when unset — keeps local/dev/test runs clean.
    """
    from backend.config import get_settings

    s = get_settings()
    if not s.sentry_dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=s.sentry_dsn,
        environment=s.sentry_environment,
        traces_sample_rate=s.sentry_traces_sample_rate,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logger.info("Sentry initialized (environment=%s)", s.sentry_environment)
    return True
